"""Dynamic tool loader — imports tool classes from 'module:ClassName' specs."""

from __future__ import annotations

import importlib
import inspect
import typing
from typing import Any

from loguru import logger
from kosong.tooling.simple import SimpleToolset, ToolType

from closeclaw.agent_core.runtime import Runtime


def load_tools(specs: list[str], runtime: Runtime) -> SimpleToolset:
    """Load tools from ``'module.path:ClassName'`` strings.

    Each tool is instantiated with *runtime* injected into any positional
    parameter annotated as ``Runtime``.  Tools that cannot be loaded are
    skipped with a warning.
    """
    toolset = SimpleToolset()
    for spec in specs:
        try:
            tool = _load_one(spec, runtime)
            if tool is not None:
                toolset += tool
                logger.debug("Loaded tool: {spec}", spec=spec)
        except Exception as exc:
            logger.warning("Skipping tool {spec}: {exc}", spec=spec, exc=exc)
    return toolset


def _load_one(spec: str, runtime: Runtime) -> ToolType | None:
    if ":" not in spec:
        raise ValueError(f"Invalid tool spec (expected 'module:Class'): {spec}")
    module_path, class_name = spec.rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    # Check if __init__ needs Runtime
    if "__init__" in cls.__dict__:
        sig = inspect.signature(cls)
        try:
            hints = typing.get_type_hints(cls.__init__)
        except Exception:
            hints = {}
        args: list[Any] = []
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.KEYWORD_ONLY:
                break
            annotation = hints.get(param.name, param.annotation)
            if annotation is inspect.Parameter.empty:
                continue
            if annotation is Runtime:
                args.append(runtime)
            elif param.default is not inspect.Parameter.empty:
                break
            else:
                raise TypeError(f"Unknown dependency {annotation} for {class_name}")
        return cls(*args)
    return cls()
