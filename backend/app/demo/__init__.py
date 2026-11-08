"""Public demo environment: a self-contained, synthetic Continuum workspace.

Everything in this package is generated demonstration data. It contains no
personal information, no private repositories, no access tokens and no
confidential project documents — only a fictional "Payment Gateway System"
used to let a judge explore the product without creating an account.
"""

from __future__ import annotations

from app.demo.seeder import (
    DEMO_BANNER_LABEL,
    DEMO_DATA_DISCLAIMER,
    DemoSeedResult,
    demo_project_name,
    demo_workspace_name,
    ensure_demo_data,
    reset_demo_data,
)

__all__ = [
    "DEMO_BANNER_LABEL",
    "DEMO_DATA_DISCLAIMER",
    "DemoSeedResult",
    "demo_project_name",
    "demo_workspace_name",
    "ensure_demo_data",
    "reset_demo_data",
]
