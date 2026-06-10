from __future__ import annotations

import argparse
import inspect
import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FILES = (
    "policy.py",
    "train.py",
    "infer.py",
    "default_config.yaml",
    "search_space.yaml",
    "algorithm_card.md",
    "requirements.txt",
    "manifest.json",
)

REQUIRED_METHODS = ("reset", "act", "load", "get_config_schema")
DUMMY_ENV_SPEC = {
    "action_space": {"shape": [4], "low": [-1.0, -1.0, -1.0, -1.0], "high": [1.0, 1.0, 1.0, 1.0]},
    "observation_space": {"shape": [12], "low": [-10.0] * 12, "high": [10.0] * 12},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a generated policy package.")
    parser.add_argument("--policy", required=True)
    args = parser.parse_args()

    errors = validate_policy(Path(args.policy))
    if errors:
        print("policy validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("policy validation passed")
    return 0


def validate_policy(policy_dir: Path) -> list[str]:
    errors: list[str] = []
    if not policy_dir.is_dir():
        return [f"policy directory does not exist: {policy_dir}"]

    errors.extend(_missing_files(policy_dir, REQUIRED_FILES))
    if errors:
        return errors

    contract = _load_real_contract_policy(errors)
    if contract is None:
        return errors

    PolicyClass = _load_policy_class(policy_dir / "policy.py", errors)
    if PolicyClass is None:
        return errors

    _validate_policy_protocol(PolicyClass, contract, errors)
    policy = _instantiate_policy(PolicyClass, errors)
    if policy is None:
        return errors

    schema = _get_config_schema(policy, errors)
    search_space = _read_yaml_mapping(policy_dir / "search_space.yaml", errors)
    _validate_search_space_schema(search_space, schema, errors)
    return errors


def _missing_files(root: Path, filenames: tuple[str, ...]) -> list[str]:
    return [f"missing required file: {name}" for name in filenames if not (root / name).is_file()]


def _load_policy_class(policy_path: Path, errors: list[str]) -> type | None:
    repo_root = Path(__file__).resolve().parents[1]
    old_sys_path = list(sys.path)
    try:
        module_name = f"_validated_policy_{abs(hash(policy_path.resolve()))}"
        spec = importlib.util.spec_from_file_location(module_name, policy_path)
        if spec is None or spec.loader is None:
            errors.append(f"cannot load policy module: {policy_path}")
            return None
        module = importlib.util.module_from_spec(spec)
        sys.path = [str(repo_root), str(policy_path.parent), *old_sys_path]
        spec.loader.exec_module(module)
    except Exception as error:
        errors.append(f"cannot import policy.py: {error}")
        return None
    finally:
        sys.path = old_sys_path

    PolicyClass = getattr(module, "PolicyClass", None)
    if not isinstance(PolicyClass, type):
        errors.append("policy.py must define PolicyClass")
        return None
    return PolicyClass


def _validate_policy_protocol(PolicyClass: type, contract: type, errors: list[str]) -> None:
    try:
        if not issubclass(PolicyClass, contract):
            errors.append("PolicyClass must subclass real contracts Policy")
    except TypeError:
        errors.append("PolicyClass is not a valid class for contract checking")


def _load_real_contract_policy(errors: list[str]) -> type | None:
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "policy_protocol.py"
    try:
        spec = importlib.util.spec_from_file_location("contracts.policy_protocol", contract_path)
        if spec is None or spec.loader is None:
            errors.append(f"cannot load real policy contract: {contract_path}")
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules["contracts.policy_protocol"] = module
        spec.loader.exec_module(module)
    except Exception as error:
        errors.append(f"cannot import real policy contract: {error}")
        return None

    Policy = getattr(module, "Policy", None)
    if not isinstance(Policy, type):
        errors.append("real policy contract must define Policy")
        return None
    return Policy


def _instantiate_policy(PolicyClass: type, errors: list[str]) -> Any | None:
    try:
        signature = inspect.signature(PolicyClass)
    except (TypeError, ValueError) as error:
        errors.append(f"cannot inspect PolicyClass constructor: {error}")
        return None

    for args in (({}, DUMMY_ENV_SPEC), ({},), tuple()):
        try:
            signature.bind(*args)
        except TypeError:
            continue
        try:
            return PolicyClass(*args)
        except Exception as error:
            errors.append(f"PolicyClass instantiation failed: {type(error).__name__}: {error}")
            return None
    errors.append("PolicyClass could not be instantiated with supported signatures")
    return None


def _get_config_schema(policy: Any, errors: list[str]) -> dict[str, Any]:
    try:
        schema = policy.get_config_schema()
    except Exception as error:
        errors.append(f"get_config_schema() failed: {error}")
        return {}
    if not isinstance(schema, dict):
        errors.append("get_config_schema() must return a mapping")
        return {}
    return schema


def _read_yaml_mapping(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as error:
        errors.append(f"cannot parse {path.name}: {error}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path.name} root must be a mapping")
        return {}
    return data


def _validate_search_space_schema(search_space: dict[str, Any], schema: dict[str, Any], errors: list[str]) -> None:
    parameters = search_space.get("parameters")
    if not isinstance(parameters, dict):
        errors.append("search_space.parameters must be a mapping")
        return

    missing = [name for name in parameters if name not in schema]
    if missing:
        errors.append(f"search_space parameters missing from get_config_schema(): {', '.join(sorted(missing))}")


if __name__ == "__main__":
    raise SystemExit(main())
