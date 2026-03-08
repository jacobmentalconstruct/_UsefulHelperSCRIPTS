import importlib
import json
from pathlib import Path

SERVICE_SPECS = [{'service_id': 'service_6970158b116a0e1d8301d2ed', 'class_name': 'ExplorerWidgetMS', 'service_name': 'ExplorerWidgetMS', 'module_import': 'library.microservices.ui._ExplorerWidgetMS', 'description': 'A standalone file system tree viewer widget.', 'tags': ['ui', 'filesystem', 'widget'], 'capabilities': ['ui:gui', 'filesystem:read'], 'manager_layer': '', 'registry_name': 'ExplorerWidgetMS', 'is_ui': True, 'endpoints': [{'method_name': 'get_health', 'inputs_json': '{}', 'outputs_json': '{"status": "str", "uptime": "float"}', 'description': 'Standardized health check for service status.', 'tags_json': '["diagnostic", "health"]', 'mode': 'sync'}, {'method_name': 'get_selected_paths', 'inputs_json': '{}', 'outputs_json': '{"selected_paths": "List[str]"}', 'description': 'Returns a list of currently checked folder paths.', 'tags_json': '["ui", "read"]', 'mode': 'sync'}, {'method_name': 'refresh_tree', 'inputs_json': '{}', 'outputs_json': '{}', 'description': 'Rescans the directory and refreshes the tree view.', 'tags_json': '["ui", "refresh"]', 'mode': 'sync'}]}, {'service_id': 'service_ddb133b7bba8558c2087a2e6', 'class_name': 'TkinterAppShellMS', 'service_name': 'TkinterAppShell', 'module_import': 'library.microservices.ui._TkinterAppShellMS', 'description': 'The Application Container. Manages the root window, main loop, and global layout.', 'tags': ['ui', 'core', 'lifecycle'], 'capabilities': ['ui:root', 'ui:gui'], 'manager_layer': '', 'registry_name': 'TkinterAppShell', 'is_ui': True, 'endpoints': [{'method_name': 'get_health', 'inputs_json': '{}', 'outputs_json': '{"status": "str", "uptime": "float"}', 'description': 'Standardized health check for service status.', 'tags_json': '["diagnostic", "health"]', 'mode': 'sync'}, {'method_name': 'get_main_container', 'inputs_json': '{}', 'outputs_json': '{"container": "tk.Frame"}', 'description': 'Returns the main content area for other services to dock into.', 'tags_json': '["ui", "layout"]', 'mode': 'sync'}, {'method_name': 'launch', 'inputs_json': '{}', 'outputs_json': '{}', 'description': 'Starts the GUI Main Loop.', 'tags_json': '["lifecycle", "start"]', 'mode': 'sync'}, {'method_name': 'shutdown', 'inputs_json': '{}', 'outputs_json': '{}', 'description': 'Gracefully shuts down the application.', 'tags_json': '["lifecycle", "stop"]', 'mode': 'sync'}]}, {'service_id': 'service_932c0f5222f07ed1f934841e', 'class_name': 'TkinterThemeManagerMS', 'service_name': 'TkinterThemeManager', 'module_import': 'library.microservices.ui._TkinterThemeManagerMS', 'description': 'Centralized modern Tkinter theme tokens and icon maps used by UI microservices.', 'tags': ['ui', 'config', 'theme'], 'capabilities': ['ui:style'], 'manager_layer': '', 'registry_name': 'TkinterThemeManager', 'is_ui': True, 'endpoints': [{'method_name': 'get_health', 'inputs_json': '{}', 'outputs_json': '{"icon_count": "int", "status": "str", "token_count": "int", "uptime": "float"}', 'description': 'Standardized health check for theme manager state.', 'tags_json': '["diagnostic", "health"]', 'mode': 'sync'}, {'method_name': 'get_legacy_aliases', 'inputs_json': '{}', 'outputs_json': '{"aliases": "dict"}', 'description': 'Return legacy theme alias map for compatibility with older Tkinter components.', 'tags_json': '["ui", "read", "compat"]', 'mode': 'sync'}, {'method_name': 'get_node_icons', 'inputs_json': '{}', 'outputs_json': '{"icons": "dict"}', 'description': 'Return active node icon map.', 'tags_json': '["ui", "read"]', 'mode': 'sync'}, {'method_name': 'get_theme', 'inputs_json': '{}', 'outputs_json': '{"theme": "dict"}', 'description': 'Return active theme token dictionary.', 'tags_json': '["ui", "read"]', 'mode': 'sync'}, {'method_name': 'update_icon', 'inputs_json': '{"icon": "str", "node_type": "str"}', 'outputs_json': '{"ok": "bool"}', 'description': 'Update or add icon mapping for a node type.', 'tags_json': '["ui", "write"]', 'mode': 'sync'}, {'method_name': 'update_key', 'inputs_json': '{"key": "str", "value": "Any"}', 'outputs_json': '{"ok": "bool"}', 'description': 'Update a single theme token at runtime.', 'tags_json': '["ui", "write"]', 'mode': 'sync'}]}, {'service_id': 'service_56079e96662212cbe7567482', 'class_name': 'WorkbenchLayoutMS', 'service_name': 'WorkbenchLayout', 'module_import': 'library.microservices.ui._WorkbenchLayoutMS', 'description': 'A declarative layout engine that builds resizable, nested Workbenches (Rows/Cols) from a config dictionary.', 'tags': ['ui', 'layout', 'framework'], 'capabilities': ['ui:construct'], 'manager_layer': '', 'registry_name': 'WorkbenchLayout', 'is_ui': True, 'endpoints': [{'method_name': 'build_from_manifest', 'inputs_json': '{"manifest": "Dict"}', 'outputs_json': '{}', 'description': 'Builds the UI structure based on the provided dictionary layout.', 'tags_json': '["ui", "build"]', 'mode': 'sync'}, {'method_name': 'get_health', 'inputs_json': '{}', 'outputs_json': '{"status": "str", "uptime": "float"}', 'description': 'Standardized health check for service status.', 'tags_json': '["diagnostic", "health"]', 'mode': 'sync'}]}]

class BackendRuntime:
    def __init__(self):
        self.app_dir = Path(__file__).resolve().parent
        self.settings = json.loads((self.app_dir / "settings.json").read_text(encoding="utf-8"))
        self._instances = {}
        self._hub = None
        self._hub_error = ""
        if any(spec.get("manager_layer") for spec in SERVICE_SPECS):
            try:
                from library.orchestrators import LayerHub
                self._hub = LayerHub()
            except Exception as exc:
                self._hub_error = str(exc)

    def list_services(self):
        return list(SERVICE_SPECS)

    def _find_spec(self, name):
        target = str(name).strip()
        for spec in SERVICE_SPECS:
            if target in {spec["class_name"], spec["service_name"], spec["service_id"]}:
                return spec
        return None

    def get_service(self, name, config=None):
        spec = self._find_spec(name)
        if spec is None:
            raise KeyError(name)
        cache_key = spec["class_name"]
        if config is None and cache_key in self._instances:
            return self._instances[cache_key]
        if spec.get("manager_layer") and self._hub is not None:
            manager = self._hub.get_manager(spec["manager_layer"])
            if manager is not None:
                service = manager.get(spec["registry_name"]) or manager.get(spec["class_name"])
                if service is not None:
                    self._instances[cache_key] = service
                    return service
        module = importlib.import_module(spec["module_import"])
        cls = getattr(module, spec["class_name"])
        try:
            instance = cls(config or {})
        except TypeError:
            instance = cls()
        if config is None:
            self._instances[cache_key] = instance
        return instance

    def call(self, service_name, endpoint, **kwargs):
        service = self.get_service(service_name, config=kwargs.pop("_config", None))
        fn = getattr(service, endpoint)
        return fn(**kwargs)

    def health(self):
        report = {"instantiated": {}, "deferred": [], "manager_hub_error": self._hub_error}
        for spec in SERVICE_SPECS:
            if spec["class_name"] in self._instances:
                service = self._instances[spec["class_name"]]
                try:
                    report["instantiated"][spec["class_name"]] = service.get_health()
                except Exception as exc:
                    report["instantiated"][spec["class_name"]] = {"status": "error", "error": str(exc)}
            else:
                report["deferred"].append(spec["class_name"])
        return report

    def shutdown(self):
        for service in list(self._instances.values()):
            closer = getattr(service, "shutdown", None)
            if callable(closer):
                closer()
