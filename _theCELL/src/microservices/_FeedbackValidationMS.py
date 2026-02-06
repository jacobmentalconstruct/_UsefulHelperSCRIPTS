"""
SERVICE_NAME: _FeedbackValidationMS
ENTRY_POINT: _FeedbackValidationMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: sqlite3, json
"""
import sqlite3
import json
import datetime
from typing import Dict, Any, List, Optional
from .microservice_std_lib import service_metadata, service_endpoint
from .base_service import BaseService

@service_metadata(
    name='FeedbackValidation', 
    version='1.0.0', 
    description='System-level memory layer for recording HITL feedback and transaction validation.',
    tags=['hitl', 'training', 'validation', 'context'],
    capabilities=['db:sqlite', 'training-data:export'],
    side_effects=['db:write'],
    internal_dependencies=['base_service', 'microservice_std_lib']
)
class FeedbackValidationMS(BaseService):
    """
    The Validator: Records accepted/rejected transactions into a dedicated
    training table within the knowledge graph for future prompt context.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__('FeedbackValidation')
        self.config = config or {}
        self.db_path = self.config.get('db_path', 'knowledge.db')
        self._init_training_table()

    def _init_training_table(self):
        """Ensures the knowledge graph can store validated transactions."""
        conn = sqlite3.connect(self.db_path)
        # Create a specific table for training pairs
        conn.execute('''
            CREATE TABLE IF NOT EXISTS training_data (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                prompt TEXT,
                response TEXT,
                is_accepted INTEGER,
                metadata_json TEXT
            )
        ''')
        conn.close()

    @service_endpoint(
        inputs={'prompt': 'str', 'response': 'str', 'is_accepted': 'bool', 'meta': 'Dict'},
        outputs={'success': 'bool'},
        description='Records a validated or rejected transaction as training context.',
        tags=['write', 'hitl'],
        side_effects=['db:write']
    )
    def submit_feedback(self, prompt: str, response: str, is_accepted: bool, meta: Dict = None) -> bool:
        """
        Main entry point for the HITL UI to deposit the result of an inference turn.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            timestamp = datetime.datetime.utcnow().isoformat()
            
            # 1. Insert into raw training table
            cursor.execute(
                'INSERT INTO training_data (timestamp, prompt, response, is_accepted, metadata_json) VALUES (?, ?, ?, ?, ?)',
                (timestamp, prompt, response, 1 if is_accepted else 0, json.dumps(meta or {}))
            )
            
            # 2. Also register as a Graph Node for high-level mapping
            node_id = f"tx_{cursor.lastrowid}"
            cursor.execute(
                'INSERT OR REPLACE INTO graph_nodes (id, type, label, data_json) VALUES (?, ?, ?, ?)',
                (node_id, 'validated_transaction', f"Feedback: {'Accepted' if is_accepted else 'Rejected'}", json.dumps({'is_accepted': is_accepted}))
            )
            
            conn.commit()
            conn.close()
            self.log_info(f"Transaction recorded: {'ACCEPTED' if is_accepted else 'REJECTED'}")
            return True
        except Exception as e:
            self.log_error(f"Failed to record feedback: {e}")
            return False

    @service_endpoint(
        inputs={'limit': 'int', 'only_accepted': 'bool'},
        outputs={'history': 'List[Dict]'},
        description='Retrieves past validated transactions to build few-shot prompts.',
        tags=['read', 'prompt-builder'],
        side_effects=['db:read']
    )
    def get_validated_context(self, limit: int = 5, only_accepted: bool = True) -> List[Dict]:
        """
        Called by the system building the prompt to find 'Gold Standard' examples.
        """
        conn = sqlite3.connect(self.db_path)
        query = "SELECT prompt, response FROM training_data WHERE 1=1"
        if only_accepted:
            query += " AND is_accepted = 1"
        query += " ORDER BY id DESC LIMIT ?"
        
        results = conn.execute(query, (limit,)).fetchall()
        conn.close()
        
        return [{"prompt": r[0], "response": r[1]} for r in results]
