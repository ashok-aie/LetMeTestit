"""
LangGraph Checkpointer Factories.
Provides SQLite and in-memory persistence savers for workflow state tracking and recovery.
Includes PydanticSqliteSaver to safely serialize Pydantic models stored in node writes/metadata.
"""
import json
from pathlib import Path
import sqlite3
from typing import Optional, Any
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, ChannelVersions
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver, get_checkpoint_metadata


def safe_json_default(obj: Any) -> Any:
    """Recursively serializes Pydantic models and other non-standard objects to JSON-friendly primitives."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


class PydanticSqliteSaver(SqliteSaver):
    """
    Enhanced SqliteSaver that safely serializes Pydantic models present in
    intermediate task execution writes and state metadata.
    """

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"]["checkpoint_ns"]
        type_, serialized_checkpoint = self.serde.dumps_typed(checkpoint)
        serialized_metadata = json.dumps(
            get_checkpoint_metadata(config, metadata),
            default=safe_json_default,
            ensure_ascii=False,
        ).encode("utf-8", "ignore")

        with self.cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(config["configurable"]["thread_id"]),
                    checkpoint_ns,
                    checkpoint["id"],
                    config["configurable"].get("checkpoint_id"),
                    type_,
                    serialized_checkpoint,
                    serialized_metadata,
                ),
            )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }


def get_memory_checkpointer() -> MemorySaver:
    """
    Returns an ephemeral in-memory checkpointer suitable for unit testing
    and fast single-session runs.
    """
    return MemorySaver()


def get_sqlite_checkpointer(db_path: str = "artifacts/testpilot.db") -> PydanticSqliteSaver:
    """
    Returns a durable SQLite checkpointer that persists workflow checkpoints across
    process reloads and human-in-the-loop interruptions.

    Ensures the target directory exists and runs table setup migrations.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    saver = PydanticSqliteSaver(conn)
    saver.setup()
    return saver

