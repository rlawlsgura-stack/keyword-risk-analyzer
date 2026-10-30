"""Streamlit Community Cloud entrypoint for FIXED313."""
from pathlib import Path
import inspect
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# A long-lived Streamlit process can retain repository.py from an older app
# revision in sys.modules after the entrypoint reloads. Re-import the project
# module when its cache is stale or came from a different path.
cached_repository = sys.modules.get("repository")
if cached_repository is not None:
    cached_path = getattr(cached_repository, "__file__", None)
    expected_path = (ROOT / "repository.py").resolve()
    required_methods = (
        "load_unmatched_terms",
        "mutate_own_keyword_inquiry",
        "submit_unmatched_registration_requests",
        "load_unmatched_registration_requests",
        "delete_unmatched_registration_requests",
        "submit_new_keyword_registration_requests",
        "reject_unmatched_registration_requests",
    )
    repository_class = getattr(cached_repository, "SupabaseRepository", None)
    try:
        repository_supports_sort = "sort" in inspect.signature(
            repository_class.load_unmatched_terms
        ).parameters
    except (AttributeError, TypeError, ValueError):
        repository_supports_sort = False
    if (not cached_path or Path(cached_path).resolve() != expected_path
            or any(not hasattr(repository_class, method) for method in required_methods)
            or not repository_supports_sort):
        sys.modules.pop("repository", None)

runpy.run_path(str(ROOT / "keyword_app2_fixed313.py"), run_name="__main__")
