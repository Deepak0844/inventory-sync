"""Per-Supplier selectors and texts that drive login and extraction.

Phase 1 builds this in code; Phase 2 loads the same shape from the Supplier's
JSON flow. Not responsible for running anything.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SupplierFlow:
    """Everything the login and extract steps need to know about one Supplier."""

    base_url: str
    login_path: str
    account_path: str
    username_selector: str
    password_selector: str
    submit_selector: str
    code_prompt_text: str
    code_selector: str
    logged_in_marker: str
    blocked_text: str
    stock_selector: str
    in_stock_texts: tuple[str, ...]
    out_of_stock_texts: tuple[str, ...]
    mail_sender: str
    mail_code_pattern: str
