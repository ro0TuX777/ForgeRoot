import os
import ansible_runner
from ansible.inventory.manager import InventoryManager
from ansible.parsing.dataloader import DataLoader
from ansible.playbook import Play
from ansible.playbook.playbook import Playbook
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.plugins.callback import CallbackBase
from ansible import context

class AnsibleService:
    def __init__(self):
        self.inventory_path = os.path.join(os.path.dirname(__file__), '../ansible/inventory/hosts.ini')
        self.playbook_dir = os.path.join(os.path.dirname(__file__), '../ansible/playbooks')
        
        # Ensure ansible logs directory exists with proper permissions
        self.log_dir = '/backend/logs'
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Initialize ansible components
        self.loader = DataLoader()
        
    async def run_playbook(self, playbook_name, extra_vars=None):
        try:
            # Set up the inventory
            if not os.path.exists(self.inventory_path):
                # Create default inventory if it doesn't exist
                self._create_default_inventory()
            
            # Run the playbook
            result = ansible_runner.run(
                playbook=os.path.join(self.playbook_dir, playbook_name),
                inventory=self.inventory_path,
                extravars=extra_vars or {},
                quiet=True
            )
            
            return {
                'status': 'success' if result.rc == 0 else 'failed',
                'rc': result.rc,
                'events': result.events
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _create_default_inventory(self):
        # Create the inventory directory if it doesn't exist
        os.makedirs(os.path.dirname(self.inventory_path), exist_ok=True)
        
        # Create a basic inventory file with localhost
        with open(self.inventory_path, 'w') as f:
            f.write("""[local]
localhost ansible_connection=local

[all:vars]
ansible_python_interpreter=/usr/bin/python3
""")

# Create singleton instance
ansible_service = AnsibleService()
