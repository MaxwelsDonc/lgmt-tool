from .equivalence import (
    MRE11,
    MRE12,
    MRE13,
    MRE14,
    MRE15,
    MRE16,
    MRE21,
    MRE22,
    MRE23,
    MRE24,
)
from .symbol import MRS1, MRS2
from .premise import MRP1, MRP2, MRP3, MRP4, MRP5
from .conclusion import MRC1, MRC2, MRC3

__all__ = [
    "MRS1",
    "MRS2",
    "MRP1",
    "MRP2",
    "MRP3",
    "MRP4",
    "MRP5",
    "MRC1",
    "MRC2",
    "MRC3",
    "MRE11",
    "MRE12",
    "MRE13",
    "MRE14",
    "MRE15",
    "MRE16",
    "MRE21",
    "MRE22",
    "MRE23",
    "MRE24",
]


def _discover_additional():
    """Auto-discover MR classes added to the subpackages without editing
    this file.

    Explicit imports above guarantee the canonical 20 in a stable order;
    this scan picks up any ``MetamorphicRelation`` subclass defined in a
    module under ``lgmt.mrs`` that is not already registered. It runs after
    the explicit imports, so every module it imports is fully loadable and
    there is no circular-import risk.
    """
    import importlib
    import inspect
    import pkgutil

    from lgmt.core.structure import MetamorphicRelation

    found = []
    for module_info in pkgutil.iter_modules(__path__):
        if not module_info.ispkg:
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        for sub in pkgutil.iter_modules(module.__path__):
            if sub.name.startswith("_"):
                continue
            submodule = importlib.import_module(
                f"{__name__}.{module_info.name}.{sub.name}"
            )
            for _name, obj in inspect.getmembers(submodule, inspect.isclass):
                if (
                    issubclass(obj, MetamorphicRelation)
                    and obj is not MetamorphicRelation
                    and obj.__module__ == submodule.__name__
                ):
                    found.append(obj)
    return found


def _build_registries():
    classes: dict = {name: globals()[name] for name in __all__}
    seen_indexes = {cls().index for cls in classes.values()}
    extra = []
    for cls in _discover_additional():
        if cls.__name__ in classes:
            continue
        try:
            instance = cls()
        except Exception:
            continue  # MRs must be instantiable without arguments
        if instance.index in seen_indexes:
            continue
        seen_indexes.add(instance.index)
        classes[cls.__name__] = cls
        extra.append(cls.__name__)
    return classes, extra


MR_CLASS_REGISTRY, _DISCOVERED = _build_registries()

__all__ = __all__ + _DISCOVERED

#: All metamorphic relations, instantiated (explicit 20 first, discovered
#: extras after, each in a stable order).
ALL_MRS = [cls() for cls in MR_CLASS_REGISTRY.values()]

#: Registry mapping MR index (e.g. "MR-E1.5") to the relation instance.
MR_INDEX_REGISTRY = {mr.index: mr for mr in ALL_MRS}


def get_mr(name_or_index: str):
    """Resolve an MR instance by class name (``MRE15``) or index (``MR-E1.5``)."""
    key = name_or_index.strip()
    if key in MR_CLASS_REGISTRY:
        return MR_CLASS_REGISTRY[key]()
    if key in MR_INDEX_REGISTRY:
        return MR_INDEX_REGISTRY[key]
    # allow fuzzy match, e.g. "E15" or "mre15"
    norm = key.upper().replace("MR-", "").replace("MR", "")
    for cls_name, cls in MR_CLASS_REGISTRY.items():
        if cls_name.upper().replace("MR", "") == norm:
            return cls()
    for idx, mr in MR_INDEX_REGISTRY.items():
        if idx.upper().replace("MR-", "") == norm:
            return mr
    raise KeyError(f"Unknown MR: {name_or_index!r}")
