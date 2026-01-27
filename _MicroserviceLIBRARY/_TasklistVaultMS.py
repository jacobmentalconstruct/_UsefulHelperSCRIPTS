import sqlite3
import uuid
import logging
import datetime
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
from microservice_std_lib import service_metadata, service_endpoint
DB_PATH = Path(__file__).parent / 'task_vault.db'
logger = logging.getLogger('TaskVault')
TaskStatus = Literal['Pending', 'Running', 'Complete', 'Error', 'Awaiting-Approval']

@service_metadata(name='TaskVault', version='1.0.0', description='Persistent SQLite engine for hierarchical task management.', tags=['tasks', 'db', 'project-management'], capabilities=['db:sqlite', 'filesystem:read', 'filesystem:write'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class TasklistVaultMS:
    """
    The Taskmaster: A persistent SQLite engine for hierarchical task management.
    Supports infinite nesting of sub-tasks and status tracking.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.db_path = self.config.get('db_path', DB_PATH)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute('\n                CREATE TABLE IF NOT EXISTS task_lists (\n                    id TEXT PRIMARY KEY,\n                    name TEXT NOT NULL,\n                    created_at TIMESTAMP\n                )\n            ')
            conn.execute("\n                CREATE TABLE IF NOT EXISTS tasks (\n                    id TEXT PRIMARY KEY,\n                    list_id TEXT NOT NULL,\n                    parent_id TEXT,\n                    content TEXT NOT NULL,\n                    status TEXT DEFAULT 'Pending',\n                    result TEXT,\n                    created_at TIMESTAMP,\n                    updated_at TIMESTAMP,\n                    FOREIGN KEY(list_id) REFERENCES task_lists(id) ON DELETE CASCADE,\n                    FOREIGN KEY(parent_id) REFERENCES tasks(id) ON DELETE CASCADE\n                )\n            ")

    @service_endpoint(inputs={'name': 'str'}, outputs={'list_id': 'str'}, description='Creates a new task list and returns its ID.', tags=['tasks', 'create'], side_effects=['db:write'])
    def create_list(self, name: str) -> str:
        """Creates a new task list and returns its ID."""
        list_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow()
        with self._get_conn() as conn:
            conn.execute('INSERT INTO task_lists (id, name, created_at) VALUES (?, ?, ?)', (list_id, name, now))
        logger.info(f"Created Task List: '{name}' ({list_id})")
        return list_id

    @service_endpoint(inputs={}, outputs={'lists': 'List[Dict]'}, description='Returns metadata for all task lists.', tags=['tasks', 'read'], side_effects=['db:read'])
    def get_lists(self) -> List[Dict[str, Any]]:
        """Returns metadata for all task lists."""
        with self._get_conn() as conn:
            rows = conn.execute('SELECT * FROM task_lists ORDER BY created_at DESC').fetchall()
            return [dict(r) for r in rows]

    @service_endpoint(inputs={'list_id': 'str', 'content': 'str', 'parent_id': 'Optional[str]'}, outputs={'task_id': 'str'}, description='Adds a task (or sub-task) to a list.', tags=['tasks', 'write'], side_effects=['db:write'])
    def add_task(self, list_id: str, content: str, parent_id: Optional[str]=None) -> str:
        """Adds a task (or sub-task) to a list."""
        task_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow()
        with self._get_conn() as conn:
            conn.execute('INSERT INTO tasks (id, list_id, parent_id, content, status, created_at, updated_at) \n                   VALUES (?, ?, ?, ?, ?, ?, ?)', (task_id, list_id, parent_id, content, 'Pending', now, now))
        return task_id

    @service_endpoint(inputs={'task_id': 'str', 'content': 'str', 'status': 'str', 'result': 'str'}, outputs={}, description="Updates a task's details.", tags=['tasks', 'update'], side_effects=['db:write'])
    def update_task(self, task_id: str, content: str=None, status: TaskStatus=None, result: str=None):
        """Updates a task's details."""
        updates = []
        params = []
        if content:
            updates.append('content = ?')
            params.append(content)
        if status:
            updates.append('status = ?')
            params.append(status)
        if result:
            updates.append('result = ?')
            params.append(result)
        if not updates:
            return
        updates.append('updated_at = ?')
        params.append(datetime.datetime.utcnow())
        params.append(task_id)
        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
        with self._get_conn() as conn:
            conn.execute(sql, params)
        logger.info(f'Updated task {task_id}')

    @service_endpoint(inputs={'list_id': 'str'}, outputs={'tree': 'Dict[str, Any]'}, description='Fetches a list and reconstructs the full hierarchy of tasks.', tags=['tasks', 'read'], side_effects=['db:read'])
    def get_full_tree(self, list_id: str) -> Dict[str, Any]:
        """
        Fetches a list and reconstructs the full hierarchy of tasks.
        """
        with self._get_conn() as conn:
            list_row = conn.execute('SELECT * FROM task_lists WHERE id = ?', (list_id,)).fetchone()
            if not list_row:
                return {}
            task_rows = conn.execute('SELECT * FROM tasks WHERE list_id = ?', (list_id,)).fetchall()
        tasks_by_id = {}
        for r in task_rows:
            t = dict(r)
            t['sub_tasks'] = []
            tasks_by_id[t['id']] = t
        root_tasks = []
        for t_id, task in tasks_by_id.items():
            parent_id = task['parent_id']
            if parent_id and parent_id in tasks_by_id:
                tasks_by_id[parent_id]['sub_tasks'].append(task)
            else:
                root_tasks.append(task)
        return {'id': list_row['id'], 'name': list_row['name'], 'tasks': root_tasks}

    @service_endpoint(inputs={'list_id': 'str'}, outputs={}, description='Deletes a task list and all its tasks.', tags=['tasks', 'delete'], side_effects=['db:write'])
    def delete_list(self, list_id: str):
        with self._get_conn() as conn:
            conn.execute('DELETE FROM task_lists WHERE id = ?', (list_id,))
        logger.info(f'Deleted list {list_id}')
if __name__ == '__main__':
    import os
    test_db = Path('test_task_vault.db')
    if test_db.exists():
        os.remove(test_db)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    vault = TasklistVaultMS({'db_path': test_db})
    print('Service ready:', vault)
    plan_id = vault.create_list('System Upgrade Plan')
    t1 = vault.add_task(plan_id, 'Backup Database')
    t2 = vault.add_task(plan_id, 'Update Server')
    t2_1 = vault.add_task(plan_id, 'Stop Services', parent_id=t2)
    t2_2 = vault.add_task(plan_id, 'Run Installer', parent_id=t2)
    vault.update_task(t1, status='Complete', result='Backup saved to /tmp/bk.tar')
    vault.update_task(t2_1, status='Running')
    tree = vault.get_full_tree(plan_id)
    print(f"\n--- {tree.get('name')} ---")

    def print_node(node, indent=0):
        status_icon = '✓' if node['status'] == 'Complete' else '○'
        print(f"{'  ' * indent}{status_icon} {node['content']} [{node['status']}]")
        for child in node['sub_tasks']:
            print_node(child, indent + 1)
    if 'tasks' in tree:
        for task in tree['tasks']:
            print_node(task)
    if test_db.exists():
        os.remove(test_db)
