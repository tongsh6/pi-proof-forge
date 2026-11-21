"""Explicit per-fact scope inside the existing evidence review snapshot."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from tools.infra.evidence_sources import field_values

KEY = "fact_scope_v1"
_POSITION = {"field", "index", "value"}
_CLAIM = _POSITION | {"source", "attribution", "target", "environment", "implementation", "release"}
_ATTRIBUTIONS = {"self", "team_lead", "contributor", "teammate", "unknown"}



def checked_result_review(review, *, value, source_quote):
    """Validate only the server result protocol and its exact textual binding."""
    if not isinstance(value, str) or not value or not isinstance(source_quote, str) or source_quote.count(value) != 1:
        raise ValueError("result_review_ambiguous_source")
    if (not isinstance(review, dict)
            or review.keys() != {"outcome", "measurement_quote", "rationale"}
            or review["outcome"] not in ("established", "not_established", "unknown")
            or not isinstance(review["rationale"], str) or not review["rationale"].strip()):
        raise ValueError("result_review_invalid")
    quote = review["measurement_quote"]
    if quote is not None:
        if (review["outcome"] != "established" or not isinstance(quote, str) or not quote.strip()
                or value.count(quote) != 1 or source_quote.count(quote) != 1):
            raise ValueError("result_review_invalid_measurement_binding")
    return dict(review)


def result_review_input(card_id, claim, rows, bindings, refs, documents):
    """Project the existing current fact dependencies; never include prior verdicts."""
    position = tuple(claim[key] for key in ("field", "index", "value"))
    if claim["field"] != "results":
        raise ValueError("result_review_invalid_position")
    peers = [row for row in rows
             if tuple(row[key] for key in ("field", "index", "value")) == position]
    related = [{key: binding[key] for key in ("field", "value", "material_id", "document_id", "quote")}
               for binding in bindings
               if (binding["field"], binding["value"]) == (claim["field"], claim["value"])]
    references = {(ref["material_id"], ref["document_id"]): ref for ref in refs}
    source_documents = []
    for key in sorted({(binding["material_id"], binding["document_id"]) for binding in related}):
        ref, text = references.get(key), documents.get(key)
        if (ref is None or not isinstance(text, str)
                or hashlib.sha256(text.encode()).hexdigest() != ref["sha256"]):
            raise ValueError("fact_scope_source_unverified")
        source_documents.append({"material_id": key[0], "document_id": key[1],
                                 "sha256": ref["sha256"], "text": text})
    if not peers or not related:
        raise ValueError("fact_scope_source_unverified")
    return {"fact": {"card_id": card_id, **{key: claim[key] for key in ("field", "index", "value")}},
            "bindings": related, "documents": source_documents,
            "scopes": [{**{key: row[key] for key in sorted(_CLAIM)}, "review_index": index}
                       for index, row in enumerate(peers)]}


def result_review_basis(review_input):
    """Bind one review to its current raw dependency set, independent of display order."""
    def canonical(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def members(values):
        return sorted({canonical(value) for value in values})

    basis = {"protocol": "result-review-current-fact-v1", "fact": review_input["fact"],
             "bindings": members(review_input["bindings"]),
             "documents": members({key: doc[key] for key in ("material_id", "document_id", "sha256")}
                                  for doc in review_input["documents"]),
             "scopes": members({key: value for key, value in scope.items() if key != "review_index"}
                               for scope in review_input["scopes"])}
    return hashlib.sha256(canonical(basis).encode()).hexdigest()


def _position(item, fields):
    field, index, value = (item.get(k) for k in ("field", "index", "value"))
    if field not in ("actions", "results") or type(index) is not int or not isinstance(value, str):
        raise ValueError("fact_scope_invalid_position")
    values = field_values(fields, field)
    if not 0 <= index < len(values) or values[index] != value or values.count(value) != 1:
        raise ValueError("fact_scope_invalid_position")
    return field, index, value


def _bound(item, fields, bindings, refs):
    if not isinstance(item, dict):
        raise ValueError("fact_scope_invalid")
    field, _, value = _position(item, fields)
    source = item.get("source")
    if not isinstance(source, dict) or source.keys() != {"material_id", "document_id", "sha256", "quote"}:
        raise ValueError("fact_scope_unbound")
    if (not any(all(r.get(k) == source[k] for k in ("material_id","document_id","sha256")) for r in refs)
            or not any(b.get("field") == field and b.get("value") == value
                       and all(b.get(k) == source[k] for k in ("material_id","document_id","quote")) for b in bindings)):
        raise ValueError("fact_scope_unbound")
    return item


def _unique_source(item, documents):
    source = item["source"]
    quote = source["quote"]
    text = documents.get((source["material_id"], source["document_id"]), "")
    return bool(quote) and text.find(quote) >= 0 and text.find(quote) == text.rfind(quote)


def _require_unique_sources(rows, documents):
    if any(not _unique_source(row, documents) for row in rows):
        raise ValueError("fact_scope_source_not_unique")
    return rows


def _checked(item, fields, bindings, refs):
    if not isinstance(item, dict) or item.keys() != _CLAIM:
        raise ValueError("fact_scope_invalid")
    _bound(item, fields, bindings, refs)
    target, relation = item["target"], item["attribution"]
    if (not isinstance(relation, str) or relation not in _ATTRIBUTIONS
            or not isinstance(target, str) or not target.strip() or len(target) > 160
            or target != " ".join(target.split())):
        raise ValueError("fact_scope_invalid")
    imp, release, env = (item[k] for k in ("implementation","release","environment"))
    if (imp not in ("implemented","planned","not_implemented","unknown")
            or release not in ("released","not_released","unknown")
            or env not in ("test","staging","production","unknown")
            or (relation == imp == release == "unknown")
            or (env == "unknown" and release != "unknown")
            or (release == "released" and imp in ("planned","not_implemented"))):
        raise ValueError("fact_scope_invalid")
    return item



def _checked_stored(item, fields, bindings, refs):
    if not isinstance(item, dict):
        raise ValueError("fact_scope_invalid")
    if "result_review" not in item:
        return _checked(item, fields, bindings, refs)
    _checked({key: value for key, value in item.items() if key != "result_review"}, fields, bindings, refs)
    if item["field"] != "results":
        raise ValueError("result_review_invalid")
    review = item["result_review"]
    if not isinstance(review, dict):
        raise ValueError("result_review_invalid")
    checked_result_review({key: val for key, val in review.items() if key != "basis_sha256"},
                          value=item["value"], source_quote=item["source"]["quote"])
    if "basis_sha256" in review:
        basis = review["basis_sha256"]
        if (not isinstance(basis, str) or len(basis) != 64
                or any(char not in "0123456789abcdef" for char in basis)):
            raise ValueError("result_review_invalid_basis")
    # A historical three-field review preserves its scope, but supplies no current authority.
    return item


def _retained(rows, fields, bindings, refs, *, validate):
    valid = []
    if not isinstance(rows, list) or len(rows) > 48:
        return valid
    for row in rows:
        try:
            checked = validate(row, fields, bindings, refs)
            if checked not in valid:
                valid.append(checked)
        except (ValueError, TypeError, AttributeError):
            continue
    return valid


def _stored_scope(scalars):
    """维护同一复审快照的既有约束，不因暂存或待复审而将其视为已撤销。"""
    try:
        snapshot = json.loads(scalars.get("reviewed_facts_json") or "{}")
    except (ValueError, TypeError) as exc:
        raise ValueError("fact_scope_invalid") from exc
    if not isinstance(snapshot, dict):
        raise ValueError("fact_scope_invalid")
    return snapshot.get(KEY, [])


def _saved(scalars):
    if scalars.get("review_decision") != "approved" or scalars.get("status") != "saved_eligible":
        return []
    try:
        return _stored_scope(scalars)
    except ValueError:
        return []


def apply_fact_scope(existing, fields, bindings, refs, directive, *, provided, documents):
    """Called only after the existing save route validates all cited source documents."""
    original = {**existing["scalars"], **existing["lists"]} if existing else {}
    saved = _stored_scope(original)
    if not isinstance(saved, list):
        raise ValueError("fact_scope_invalid")
    rows = _retained(saved, fields, bindings, refs, validate=_bound)
    if not provided:
        if any(row not in rows for row in saved):
            raise ValueError("fact_scope_unverifiable")
        return _require_unique_sources(rows, documents)
    if not isinstance(directive, dict):
        raise ValueError("fact_scope_invalid")
    kind = directive.get("kind")
    claim = {k:v for k,v in directive.items() if k != "kind"}
    position = _position(claim, original)
    if _position(claim, fields) != position:
        raise ValueError("fact_scope_invalid_position")
    def same_position(row):
        return isinstance(row, dict) and tuple(row.get(k) for k in ("field","index","value")) == position
    if any(row not in rows and not same_position(row) for row in saved):
        raise ValueError("fact_scope_unverifiable")
    if kind == "revoke" and claim.keys() == _POSITION:
        return _require_unique_sources([row for row in rows if not same_position(row)], documents)
    if kind != "adopt":
        raise ValueError("fact_scope_invalid")
    claim = _checked(claim, fields, bindings, refs)
    classified = [row for row in _retained(rows, fields, bindings, refs, validate=_checked_stored)
                  if _unique_source(row, documents)]
    rows = [row for row in rows if not (same_position(row) and (row not in classified
            or all(row[k] == claim[k] for k in ("source","target","environment"))))]
    if len(rows) >= 48:
        raise ValueError("fact_scope_limit")
    return _require_unique_sources([*rows, claim], documents)


def _checked_rows(doc, rows, refs, bindings, documents):
    fields = {**doc["scalars"], **doc["lists"]}
    bound = _retained(rows, fields, bindings, refs, validate=_bound)
    _require_unique_sources(bound, documents)
    return _retained(bound, fields, bindings, refs, validate=_checked_stored)


def _scope_sources(rows):
    return [{**row["source"], "attribution": row["attribution"],
             "implementation": row["implementation"], "release": row["release"],
             **({"result_review": row["result_review"]} if "result_review" in row else {})} for row in rows]


def _project_scopes(card_id, rows):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = tuple(row[k] for k in ("field", "index", "value", "target", "environment"))
        # Result scopes describe separate original occurrences; differing states are not a verdict.
        key += (tuple(row[k] for k in ("attribution", "implementation", "release"))
                if row["field"] == "results" else (None, None, None))
        grouped[key][row["attribution"]].append(row)
    out = []
    for (field, index, value, target, env, _, _, _), by_relation in grouped.items():
        if field == "results":
            for relation, scoped in by_relation.items():
                first = scoped[0]
                out.append({"fact_id": f"{card_id}:{field}:{index}", "field": field, "index": index,
                            "value": value, "attribution": relation, "target": target, "environment": env,
                            "implementation": first["implementation"], "release": first["release"],
                            "sources": _scope_sources(scoped)})
            continue
        if {"self", "teammate"}.issubset(by_relation):
            # Action constraints retain their existing closed responsibility boundary.
            by_relation["conflict"] = by_relation.pop("self") + by_relation.pop("teammate")
        for relation, scoped in by_relation.items():
            implementations = {r["implementation"] for r in scoped} - {"unknown"}
            releases = {r["release"] for r in scoped} - {"unknown"}
            cross = "released" in releases and bool(implementations & {"planned", "not_implemented"})
            imp_conflict = cross or ("implemented" in implementations and len(implementations) > 1)
            implementation = ("conflict" if imp_conflict else next((state for state in
                ("implemented", "planned", "not_implemented") if state in implementations), "unknown"))
            release = "conflict" if cross or len(releases) > 1 else next(iter(releases), "unknown")
            if relation == "conflict":
                implementation = release = "unknown"
            out.append({"fact_id": f"{card_id}:{field}:{index}", "field": field, "index": index, "value": value,
                        "attribution": relation, "target": target, "environment": env,
                        "implementation": implementation, "release": release,
                        "sources": _scope_sources(scoped)})
    return out


def _review_bases(card_id, bound, checked, bindings, refs, documents):
    bases = {}
    for row in checked:
        if row["field"] != "results":
            continue
        position = tuple(row[key] for key in ("field", "index", "value"))
        if position in bases:
            continue
        peers = [peer for peer in bound
                 if tuple(peer[key] for key in ("field", "index", "value")) == position]
        if any(peer not in checked for peer in peers):
            continue
        bases[position] = result_review_basis(result_review_input(
            card_id, row, bound, bindings, refs, documents))
    return bases


def _current_review(row, bases):
    basis = bases.get(tuple(row[key] for key in ("field", "index", "value")))
    return basis is not None and row.get("result_review", {}).get("basis_sha256") == basis


def project_fact_scope(doc, refs, bindings, *, documents):
    """Show original scopes; expose a verdict only when its actual dependency set is current."""
    scalars = doc["scalars"]
    if scalars.get("candidate_pool_eligible") != "true" or not scalars.get("id"):
        return []
    bound = _saved(scalars)
    checked = _checked_rows(doc, bound, refs, bindings, documents)
    bases = _review_bases(scalars["id"], bound, checked, bindings, refs, documents)
    visible = [row if _current_review(row, bases)
               else {key: val for key, val in row.items() if key != "result_review"} for row in checked]
    return _project_scopes(scalars["id"], visible)


def _current_scope_rows(doc, material_dir, *, card_id, validated_sources=None):
    """Read the same current source snapshot for positive and negative projections."""
    scalars = doc["scalars"]
    rows = _saved(scalars)
    if not rows:
        return [], [], {}
    if scalars.get("id") != card_id:
        raise ValueError("fact_scope_card_identity_mismatch")
    from tools.infra.evidence_sources import assert_source_snapshot, validated_source_inputs

    sources = validated_source_inputs(doc, material_dir) if validated_sources is None else validated_sources
    if not sources:
        raise ValueError("fact_scope_source_unverified")
    assert_source_snapshot(sources.snapshots)
    refs = json.loads(scalars.get("source_documents_json") or "[]")
    bindings = json.loads(scalars.get("field_sources_json") or "[]")
    bound = _retained(rows, {**scalars, **doc["lists"]}, bindings, refs, validate=_bound)
    if not isinstance(rows, list) or any(row not in bound for row in rows):
        raise ValueError("fact_scope_unverifiable")
    _require_unique_sources(bound, sources.documents)
    checked = _retained(bound, {**scalars, **doc["lists"]}, bindings, refs, validate=_checked_stored)
    return bound, checked, _review_bases(card_id, bound, checked, bindings, refs, sources.documents)


def _result_reviews(card_id, checked, bases):
    """Select one independently supported original row from the current reviewed context."""
    out = {}
    for row in checked:
        if (row["field"] != "results" or row["attribution"] not in {"self", "team_lead", "contributor"}
                or row.get("result_review", {}).get("outcome") != "established"
                or not _current_review(row, bases)):
            continue
        fid = f'{card_id}:results:{row["index"]}'
        # No source vote or cross-row assembly: keep the chosen row's own verdict and quote.
        if fid not in out or (out[fid]["result_review"]["measurement_quote"] is None
                              and row["result_review"]["measurement_quote"] is not None):
            out[fid] = row
    return out


def current_result_reviews(doc, material_dir, *, card_id, validated_sources=None):
    """Current, source-bound complete results shared by both renderers and quality."""
    if doc["scalars"].get("candidate_pool_eligible") != "true":
        return {}
    bound, checked, bases = _current_scope_rows(doc, material_dir, card_id=card_id,
                                               validated_sources=validated_sources)
    return _result_reviews(card_id, checked, bases)


def personal_claim_exclusions(doc, material_dir, *, card_id, validated_sources=None):
    """Keep action scope closed; only independently established complete results open."""
    bound, checked, bases = _current_scope_rows(doc, material_dir, card_id=card_id,
                                               validated_sources=validated_sources)
    allowed = (_result_reviews(card_id, checked, bases)
               if doc["scalars"].get("candidate_pool_eligible") == "true" else {})
    return frozenset(f'{card_id}:{row["field"]}:{row["index"]}' for row in bound).difference(allowed)


def nonpersonal_reviewed_fact_ids(doc, material_dir, *, card_id, validated_sources):
    """Preserve explicit action attribution constraints; result availability is separate."""
    if doc["scalars"].get("candidate_pool_eligible") != "true":
        return frozenset()
    bound, checked, _ = _current_scope_rows(doc, material_dir, card_id=card_id,
                                           validated_sources=validated_sources)
    unknown = {f'{card_id}:{row["field"]}:{row["index"]}' for row in bound
               if row["field"] == "actions" and row not in checked}
    grouped = defaultdict(set)
    actions = [row for row in checked if row["field"] == "actions"]
    for row in _project_scopes(card_id, actions):
        grouped[row["fact_id"]].add(row["attribution"])
    return frozenset(fid for fid, relations in grouped.items()
                     if fid not in unknown and relations <= {"teammate", "conflict"})
