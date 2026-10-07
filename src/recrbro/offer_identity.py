from __future__ import annotations

import re
import unicodedata

COMPANY_IDENTITY_SUFFIXES = {
    "ag",
    "bv",
    "co",
    "com",
    "company",
    "corp",
    "corporation",
    "eu",
    "gmbh",
    "group",
    "holding",
    "holdings",
    "inc",
    "incorporated",
    "io",
    "limited",
    "llc",
    "ltd",
    "pl",
    "sa",
    "sas",
}
LEGAL_COMPANY_SUFFIXES = (
    ("sp", "z", "oo"),
    ("spolka", "z", "ograniczona", "odpowiedzialnoscia"),
)


def _identity_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.findall(r"[a-z0-9]+", normalized)


def offer_identity(title: str, company: str) -> tuple[str, str]:
    company_tokens = _identity_tokens(company)
    while company_tokens:
        matching_suffix = next(
            (
                suffix
                for suffix in LEGAL_COMPANY_SUFFIXES
                if tuple(company_tokens[-len(suffix) :]) == suffix
            ),
            None,
        )
        if matching_suffix is not None:
            del company_tokens[-len(matching_suffix) :]
            continue
        if company_tokens[-1] in COMPANY_IDENTITY_SUFFIXES:
            company_tokens.pop()
            continue
        break

    title_without_gender_marker = re.sub(
        r"[\[(]\s*[mfxd](?:\s*/\s*[mfxd])+\s*[\])]",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return " ".join(_identity_tokens(title_without_gender_marker)), " ".join(
        company_tokens
    )
