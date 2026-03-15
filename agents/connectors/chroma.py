import json
import os
import tempfile
import time
from typing import Optional

from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import JSONLoader
from langchain_community.vectorstores.chroma import Chroma

from agents.polymarket.gamma import GammaMarketClient
from agents.utils.objects import SimpleEvent, SimpleMarket


class PolymarketRAG:
    def __init__(self, local_db_directory=None, embedding_function=None) -> None:
        self.gamma_client = GammaMarketClient()
        self.local_db_directory = local_db_directory
        self.embedding_function = embedding_function

    def load_json_from_local(
        self, json_file_path=None, vector_db_directory="./local_db"
    ) -> None:
        loader = JSONLoader(
            file_path=json_file_path, jq_schema=".[].description", text_content=False
        )
        loaded_docs = loader.load()

        embedding_function = OpenAIEmbeddings(model="text-embedding-3-small")
        Chroma.from_documents(
            loaded_docs, embedding_function, persist_directory=vector_db_directory
        )

    def create_local_markets_rag(self, local_directory="./local_db") -> None:
        all_markets = self.gamma_client.get_all_current_markets()

        if not os.path.isdir(local_directory):
            os.mkdir(local_directory)

        local_file_path = f"{local_directory}/all-current-markets_{time.time()}.json"

        with open(local_file_path, "w+") as output_file:
            json.dump(all_markets, output_file)

        self.load_json_from_local(
            json_file_path=local_file_path, vector_db_directory=local_directory
        )

    def query_local_markets_rag(
        self, local_directory=None, query=None
    ) -> "list[tuple]":
        embedding_function = OpenAIEmbeddings(model="text-embedding-3-small")
        local_db = Chroma(
            persist_directory=local_directory, embedding_function=embedding_function
        )
        response_docs = local_db.similarity_search_with_score(query=query)
        return response_docs

    def events(
        self, events: "list[SimpleEvent]", prompt: str, k: Optional[int] = None
    ) -> "list[tuple]":
        if not events:
            return []

        # create local json file
        local_events_directory: str = "./local_db_events"
        local_file_path = f"{local_events_directory}/events.json"
        dict_events = [x.dict() for x in events]
        try:
            os.makedirs(local_events_directory, exist_ok=True)
            with open(local_file_path, "w+") as output_file:
                json.dump(dict_events, output_file)
        except OSError as err:
            local_events_directory = tempfile.mkdtemp(prefix="polyagents_events_")
            local_file_path = f"{local_events_directory}/events.json"
            print(
                "[rag] falling_back_to_temp_events_dir "
                f"reason={err} temp_dir={local_events_directory}"
            )
            with open(local_file_path, "w+") as output_file:
                json.dump(dict_events, output_file)

        # create vector db
        def metadata_func(record: dict, metadata: dict) -> dict:

            metadata["id"] = record.get("id")
            metadata["markets"] = record.get("markets")

            return metadata

        loader = JSONLoader(
            file_path=local_file_path,
            jq_schema=".[]",
            content_key="description",
            text_content=False,
            metadata_func=metadata_func,
        )
        loaded_docs = loader.load()
        if not loaded_docs:
            return []
        embedding_function = OpenAIEmbeddings(model="text-embedding-3-small")
        vector_db_directory = f"{local_events_directory}/chroma"
        try:
            local_db = Chroma.from_documents(
                loaded_docs, embedding_function, persist_directory=vector_db_directory
            )
        except Exception as err:
            if not self._is_writable_db_error(err):
                raise
            fallback_directory = tempfile.mkdtemp(prefix="polyagents_events_chroma_")
            print(
                "[rag] readonly_events_db_fallback "
                f"reason={err} temp_dir={fallback_directory}"
            )
            local_db = Chroma.from_documents(
                loaded_docs, embedding_function, persist_directory=fallback_directory
            )

        # query
        search_k = k if isinstance(k, int) and k > 0 else 4
        return local_db.similarity_search_with_score(query=prompt, k=search_k)

    def markets(
        self, markets: "list[SimpleMarket]", prompt: str, k: Optional[int] = None
    ) -> "list[tuple]":
        if not markets:
            return []

        # create local json file
        local_events_directory: str = "./local_db_markets"
        local_file_path = f"{local_events_directory}/markets.json"
        try:
            os.makedirs(local_events_directory, exist_ok=True)
            with open(local_file_path, "w+") as output_file:
                json.dump(markets, output_file)
        except OSError as err:
            local_events_directory = tempfile.mkdtemp(prefix="polyagents_markets_")
            local_file_path = f"{local_events_directory}/markets.json"
            print(
                "[rag] falling_back_to_temp_markets_dir "
                f"reason={err} temp_dir={local_events_directory}"
            )
            with open(local_file_path, "w+") as output_file:
                json.dump(markets, output_file)

        # create vector db
        def metadata_func(record: dict, metadata: dict) -> dict:

            metadata["id"] = record.get("id")
            metadata["outcomes"] = record.get("outcomes")
            metadata["outcome_prices"] = record.get("outcome_prices")
            metadata["question"] = record.get("question")
            metadata["clob_token_ids"] = record.get("clob_token_ids")
            metadata["volume"] = record.get("volume")
            metadata["volume24hr"] = record.get("volume24hr")
            metadata["volume_clob"] = record.get("volume_clob")
            metadata["volume24hr_clob"] = record.get("volume24hr_clob")
            metadata["liquidity"] = record.get("liquidity")
            metadata["liquidity_clob"] = record.get("liquidity_clob")
            metadata["category"] = record.get("category")
            metadata["tags"] = record.get("tags")
            metadata["event_id"] = record.get("event_id")
            metadata["event_title"] = record.get("event_title")
            metadata["event_slug"] = record.get("event_slug")

            return metadata

        loader = JSONLoader(
            file_path=local_file_path,
            jq_schema=".[]",
            content_key="description",
            text_content=False,
            metadata_func=metadata_func,
        )
        loaded_docs = loader.load()
        if not loaded_docs:
            return []
        embedding_function = OpenAIEmbeddings(model="text-embedding-3-small")
        vector_db_directory = f"{local_events_directory}/chroma"
        try:
            local_db = Chroma.from_documents(
                loaded_docs, embedding_function, persist_directory=vector_db_directory
            )
        except Exception as err:
            if not self._is_writable_db_error(err):
                raise
            fallback_directory = tempfile.mkdtemp(prefix="polyagents_markets_chroma_")
            print(
                "[rag] readonly_markets_db_fallback "
                f"reason={err} temp_dir={fallback_directory}"
            )
            local_db = Chroma.from_documents(
                loaded_docs, embedding_function, persist_directory=fallback_directory
            )

        # query
        search_k = k if isinstance(k, int) and k > 0 else 4
        return local_db.similarity_search_with_score(query=prompt, k=search_k)

    def _is_writable_db_error(self, err: Exception) -> bool:
        err_text = str(err).lower()
        return (
            "readonly database" in err_text
            or "attempt to write a readonly database" in err_text
            or "permission denied" in err_text
        )
