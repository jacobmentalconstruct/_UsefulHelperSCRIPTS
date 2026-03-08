"""Grouped microservice library package."""

__all__ = ["AppStamper", "CatalogBuilder", "LayerHub", "LibraryQueryService", "LibrarianApp"]


def __getattr__(name):
    if name in {"AppStamper", "CatalogBuilder", "LibraryQueryService", "LibrarianApp"}:
        from . import app_factory

        return getattr(app_factory, name)
    if name == "LayerHub":
        from .orchestrators import LayerHub

        return LayerHub
    raise AttributeError(name)
