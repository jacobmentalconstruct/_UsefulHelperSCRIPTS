import importlib
import json
from pathlib import Path

SERVICE_SPECS = [{'service_id': 'service_bff1ef62f6ffdb93b7d51b90', 'class_name': 'FingerprintScannerMS', 'service_name': 'FingerprintScannerMS', 'module_import': 'library.microservices.core._FingerprintScannerMS', 'description': 'Scans a directory tree and generates a deterministic SHA-256 fingerprint.', 'tags': ['scanning', 'integrity', 'hashing'], 'capabilities': ['filesystem:read'], 'manager_layer': '', 'registry_name': 'FingerprintScannerMS', 'is_ui': False, 'endpoints': [{'method_name': 'get_health', 'inputs_json': '{}', 'outputs_json': '{"status": "str", "uptime": "float"}', 'description': 'Standardized health check for service status.', 'tags_json': '["diagnostic", "health"]', 'mode': 'sync'}, {'method_name': 'scan_project', 'inputs_json': '{"root_path": "str"}', 'outputs_json': '{"state": "Dict[str, Any]"}', 'description': 'Scans the project and returns a comprehensive state object (hashes + Merkle root).', 'tags_json': '["scanning", "read"]', 'mode': 'sync'}]}]

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
