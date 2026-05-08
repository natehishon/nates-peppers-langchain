import os
from sqlmodel import create_engine
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver
from dotenv import load_dotenv

load_dotenv()

BASE_URI = os.getenv("DATABASE_URL")

engine = create_engine(BASE_URI.replace("postgresql://", "postgresql+psycopg://"))
pool = ConnectionPool(conninfo=BASE_URI, max_size=20, kwargs={"autocommit": True, "row_factory": dict_row})
checkpointer = PostgresSaver(pool)

