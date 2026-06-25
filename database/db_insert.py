from __future__ import annotations

"""Fetch ICICI eBG data and insert it into Oracle ADB.

This script:
- calls the ICICI FastAPI/ICICI gateway using the existing `icici_client.py`
- extracts the decrypted `eBGIssuanceList` and `eBGAmendList`
- inserts a parent row into `ebg_requests`
- inserts issuance rows into `ebg_issuances`
- inserts amendment rows into `ebg_amendments`

You can run it against the live API or point it at a saved JSON response file.
"""

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any

import oracledb

import config as app_config
from config.config import config as oracle_config
from icici_client import query as icici_query


ISSUANCE_SQL = """
INSERT INTO ebg_issuances (
    request_id,
    bg_ref_num,
    type_of_bg,
    bg_amount,
    bg_currency,
    bg_effective_date,
    guarantee_from_date,
    guarantee_to_date,
    claim_end_date,
    claim_lodgement_place,
    received_date,
    applicant_details,
    beneficiary_details,
    beneficiary_ifsc,
    beneficiary_bank_details,
    issuing_branch_ifsc,
    issuing_branch_name_address,
    sender_to_receiver_info,
    smsa_text,
    purpose_of_guarantee,
    description_of_contract,
    place_of_payment,
    amount_paid,
    date_of_payment,
    stamp_duty_paid,
    estamp_certificate_number,
    estamp_date,
    guarantee_form_num,
    state_code,
    to_be_held_in_demat,
    demat_account_num,
    custodian_service_provider,
    article_number,
    created_at
) VALUES (
    :request_id,
    :bg_ref_num,
    :type_of_bg,
    :bg_amount,
    :bg_currency,
    :bg_effective_date,
    :guarantee_from_date,
    :guarantee_to_date,
    :claim_end_date,
    :claim_lodgement_place,
    :received_date,
    :applicant_details,
    :beneficiary_details,
    :beneficiary_ifsc,
    :beneficiary_bank_details,
    :issuing_branch_ifsc,
    :issuing_branch_name_address,
    :sender_to_receiver_info,
    :smsa_text,
    :purpose_of_guarantee,
    :description_of_contract,
    :place_of_payment,
    :amount_paid,
    :date_of_payment,
    :stamp_duty_paid,
    :estamp_certificate_number,
    :estamp_date,
    :guarantee_form_num,
    :state_code,
    :to_be_held_in_demat,
    :demat_account_num,
    :custodian_service_provider,
    :article_number,
    :created_at
)
"""


AMENDMENT_SQL = """
INSERT INTO ebg_amendments (
    request_id,
    bg_ref_num,
    original_bg_num,
    num_of_amendment,
    amendment_date,
    amendment_details,
    date_of_issuance,
    received_date,
    remarks,
    applicant_details,
    beneficiary_details,
    beneficiary_ifsc,
    beneficiary_bank_details,
    issuing_branch_ifsc,
    issuing_branch_name_address,
    bg_amount,
    bg_expiry_date,
    bg_claim_expiry_date,
    sender_to_receiver_info,
    smsa_text,
    place_of_payment,
    amount_paid,
    date_of_payment,
    stamp_duty_paid,
    stamp_duty_amt_paid,
    estamp_certificate_number,
    estamp_date,
    state_code,
    to_be_held_in_demat,
    demat_account_num,
    custodian_service_provider,
    article_number,
    created_at
) VALUES (
    :request_id,
    :bg_ref_num,
    :original_bg_num,
    :num_of_amendment,
    :amendment_date,
    :amendment_details,
    :date_of_issuance,
    :received_date,
    :remarks,
    :applicant_details,
    :beneficiary_details,
    :beneficiary_ifsc,
    :beneficiary_bank_details,
    :issuing_branch_ifsc,
    :issuing_branch_name_address,
    :bg_amount,
    :bg_expiry_date,
    :bg_claim_expiry_date,
    :sender_to_receiver_info,
    :smsa_text,
    :place_of_payment,
    :amount_paid,
    :date_of_payment,
    :stamp_duty_paid,
    :stamp_duty_amt_paid,
    :estamp_certificate_number,
    :estamp_date,
    :state_code,
    :to_be_held_in_demat,
    :demat_account_num,
    :custodian_service_provider,
    :article_number,
    :created_at
)
"""


def _clean_number(value: Any):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(","):
        text = text[:-1]
    if "," in text and "." not in text:
        left, right = text.rsplit(",", 1)
        if right.isdigit() and 1 <= len(right) <= 2:
            text = left.replace(",", "") + "." + right
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", "")
    text = re.sub(r"[^0-9.]+", "", text)
    if not text:
        return None
    if text.endswith("."):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def _clean_int(value: Any):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _truncate(value: Any, max_len: int):
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= max_len else text[:max_len]


def _parse_date(value: Any, fmt: str):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, fmt).date()
    except ValueError:
        return None


def _parse_any_date(value: Any):
    if isinstance(value, date):
        return value
    for fmt in ("%Y%m%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        parsed = _parse_date(value, fmt)
        if parsed is not None:
            return parsed
    return None


def _normalize_demat_flag(value: Any):
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    return 1 if text.startswith(("Y", "T", "1")) else 0


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_icici_response(params: dict) -> dict:
    result = icici_query(params)
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or f"ICICI returned HTTP {result.get('status_code')}")
    return result


def extract_icici_lists(payload: dict) -> tuple[list[dict], list[dict]]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    data = data or {}
    ebg_list = data.get("eBGList", {}) or {}
    issuances = ebg_list.get("eBGIssuanceList", []) or []
    amendments = ebg_list.get("eBGAmendList", []) or []
    return issuances, amendments


def insert_request_row(conn, request_id: str):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            MERGE INTO ebg_requests r
            USING (SELECT :id AS id, :created_at AS created_at FROM dual) src
            ON (r.id = src.id)
            WHEN NOT MATCHED THEN
                INSERT (id, created_at) VALUES (src.id, src.created_at)
            """,
            {"id": request_id, "created_at": datetime.now()},
        )
    finally:
        cur.close()


def build_issuance_params(row: dict, request_id: str) -> dict:
    return {
        "request_id": request_id,
        "bg_ref_num": _truncate(row.get("bgRefNum"), 50),
        "type_of_bg": _truncate(row.get("typeOfBG"), 30),
        "bg_amount": _clean_number(row.get("bgAmount")),
        "bg_currency": _truncate(row.get("bgCurrency"), 3),
        "bg_effective_date": _parse_any_date(row.get("bgEffectiveDate")),
        "guarantee_from_date": _parse_any_date(row.get("guaranteeFromDate")),
        "guarantee_to_date": _parse_any_date(row.get("guaranteeToDate")),
        "claim_end_date": _parse_any_date(row.get("claimEndDate")),
        "claim_lodgement_place": _truncate(row.get("claimLodgementPlace"), 100),
        "received_date": _parse_any_date(row.get("receivedDate")),
        "applicant_details": row.get("applicantDetails"),
        "beneficiary_details": row.get("beneficiaryDetails"),
        "beneficiary_ifsc": _truncate(row.get("beneficiaryIFSC"), 20),
        "beneficiary_bank_details": row.get("beneficiaryBankDetails"),
        "issuing_branch_ifsc": _truncate(row.get("issuingBranchIFSC"), 20),
        "issuing_branch_name_address": row.get("issuingBranchNameAddress"),
        "sender_to_receiver_info": _truncate(row.get("senderToReceiverInfo"), 100),
        "smsa_text": row.get("smsatext"),
        "purpose_of_guarantee": _truncate(row.get("purposeOfGuarantee"), 255),
        "description_of_contract": row.get("descriptionOfContract"),
        "place_of_payment": _truncate(row.get("placeOfPayment"), 100),
        "amount_paid": _clean_number(row.get("amountPaid")),
        "date_of_payment": _parse_any_date(row.get("dateOfPayment")),
        "stamp_duty_paid": _truncate(row.get("stampDutyPaid"), 10),
        "estamp_certificate_number": _truncate(row.get("estampCertificateNumber"), 100),
        "estamp_date": _parse_any_date(row.get("estampDate")),
        "guarantee_form_num": _truncate(row.get("guaranteeFormNum"), 50),
        "state_code": _truncate(row.get("stateCode"), 10),
        "to_be_held_in_demat": _normalize_demat_flag(row.get("toBeHeldInDemat")),
        "demat_account_num": _truncate(row.get("dematAccountNum"), 50),
        "custodian_service_provider": _truncate(row.get("custodianServiceProvider"), 100),
        "article_number": _truncate(row.get("articleNumber"), 50),
        "created_at": datetime.now(),
    }


def build_amendment_params(row: dict, request_id: str) -> dict:
    return {
        "request_id": request_id,
        "bg_ref_num": _truncate(row.get("bgRefNum"), 50),
        "original_bg_num": _truncate(row.get("originalBGNum"), 50),
        "num_of_amendment": _clean_int(row.get("numOfAmendment")),
        "amendment_date": _parse_any_date(row.get("amendmentDate")),
        "amendment_details": row.get("amendmentDetails"),
        "date_of_issuance": _parse_any_date(row.get("dateOfIssuance")),
        "received_date": _parse_any_date(row.get("receivedDate")),
        "remarks": _truncate(row.get("remarks"), 255),
        "applicant_details": row.get("applicantDetails"),
        "beneficiary_details": row.get("beneficiaryDetails"),
        "beneficiary_ifsc": _truncate(row.get("beneficiaryIFSC"), 20),
        "beneficiary_bank_details": row.get("beneficiaryBankDetails"),
        "issuing_branch_ifsc": _truncate(row.get("issuingBranchIFSC"), 20),
        "issuing_branch_name_address": row.get("issuingBranchNameAddress"),
        "bg_amount": _clean_number(row.get("bgAmount")),
        "bg_expiry_date": _parse_any_date(row.get("bgExpiryDate")),
        "bg_claim_expiry_date": _parse_any_date(row.get("bgClaimExpiryDate")),
        "sender_to_receiver_info": _truncate(row.get("senderToReceiverInfo"), 100),
        "smsa_text": row.get("smsatext"),
        "place_of_payment": _truncate(row.get("placeOfPayment"), 100),
        "amount_paid": _clean_number(row.get("amountPaid")),
        "date_of_payment": _parse_any_date(row.get("dateOfPayment")),
        "stamp_duty_paid": _truncate(row.get("stampDutyPaid"), 10),
        "stamp_duty_amt_paid": _clean_number(row.get("stampDutyAmtPaid")),
        "estamp_certificate_number": _truncate(row.get("estampCertificateNumber"), 100),
        "estamp_date": _parse_any_date(row.get("estampDate")),
        "state_code": _truncate(row.get("stateCode"), 10),
        "to_be_held_in_demat": _normalize_demat_flag(row.get("toBeHeldInDemat")),
        "demat_account_num": _truncate(row.get("dematAccountNum"), 50),
        "custodian_service_provider": _truncate(row.get("custodianServiceProvider"), 100),
        "article_number": _truncate(row.get("articleNumber"), 50),
        "created_at": datetime.now(),
    }


def insert_row(conn, sql: str, params: dict):
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
    finally:
        cur.close()


def process_response(conn, response_payload: dict, request_id: str):
    issuances, amendments = extract_icici_lists(response_payload)

    issuance_count = 0
    amendment_count = 0

    insert_request_row(conn, request_id)

    for row in issuances:
        insert_row(conn, ISSUANCE_SQL, build_issuance_params(row, request_id))
        issuance_count += 1

    for row in amendments:
        insert_row(conn, AMENDMENT_SQL, build_amendment_params(row, request_id))
        amendment_count += 1

    return issuance_count, amendment_count


def parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(
        description="Fetch ICICI eBG data and store issuance/amendment rows in Oracle ADB."
    )
    parser.add_argument(
        "--json-file",
        help="Process a saved JSON response file instead of calling the live API.",
    )
    parser.add_argument(
        "--corp-id",
        default=app_config.ICICI_CORP_ID or "GUJARATM31122012",
        help="ICICI corpId",
    )
    parser.add_argument(
        "--reference-number",
        default="",
        help="ICICI referenceNumber",
    )
    parser.add_argument(
        "--from-date",
        default="01-01-2021",
        help="ICICI fromDate in DD-MM-YYYY",
    )
    parser.add_argument(
        "--to-date",
        default="01-01-2023",
        help="ICICI toDate in DD-MM-YYYY",
    )
    parser.add_argument(
        "--attachment-required",
        default="Y",
        choices=["Y", "N"],
        help="Whether attachment is required",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = parse_args(argv or sys.argv[1:])
    oracle = oracle_config.oracle

    conn = oracledb.connect(
        user=oracle.USER,
        password=oracle.PASSWORD,
        dsn=oracle.DSN,
        config_dir=oracle.CONFIG_DIR,
        wallet_location=oracle.WALLET_LOCATION,
        wallet_password=oracle.WALLET_PASSWORD,
    )

    try:
        if args.json_file:
            payload = load_json(args.json_file)
            request_id = payload.get("correlation_id") or str(uuid.uuid4())
            issuance_count, amendment_count = process_response(conn, payload, request_id)
            conn.commit()
            print(f"Inserted {issuance_count} issuance row(s) and {amendment_count} amendment row(s) from {args.json_file}")
            return

        plain_request = {
            "attachmentRequired": args.attachment_required,
            "corpId": args.corp_id,
            "fromDate": args.from_date,
            "referenceNumber": args.reference_number,
            "toDate": args.to_date,
        }

        result = fetch_icici_response(plain_request)
        request_id = result.get("correlation_id") or str(uuid.uuid4())
        response_payload = result.get("decrypted") or result.get("raw_response") or {}

        issuance_count, amendment_count = process_response(conn, response_payload, request_id)
        conn.commit()

        print(f"Request ID         : {request_id}")
        print(f"Issuances inserted : {issuance_count}")
        print(f"Amendments inserted: {amendment_count}")

    except Exception as exc:
        conn.rollback()
        print("Insert failed")
        print(f"Error: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
