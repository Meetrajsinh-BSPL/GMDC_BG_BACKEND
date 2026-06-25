from __future__ import annotations

import json
import sys
from datetime import datetime

import oracledb

from config.config import config


# ============================================================
# ISSUANCE INSERT SQL
# ============================================================

INSERT_ISSUANCE_SQL = """
INSERT INTO EBG_ISSUANCES_MJ (
    
    AMOUNT_PAID,
    APPLICANT_DETAILS,
    ARTICLE_NUMBER,
    BENEFICIARY_BANK_DETAILS,
    BENEFICIARY_DETAILS,
    BENEFICIARY_IFSC,
    BG_AMOUNT,
    BG_CURRENCY,
    BG_EFFECTIVE_DATE,
    BG_REF_NUM,
    CLAIM_END_DATE,
    CLAIM_LODGEMENT_PLACE,
    CUSTODIAN_SERVICE_PROVIDER,
    DATE_OF_PAYMENT,
    DEMAT_ACCOUNT_NUM,
    DESCRIPTION_OF_CONTRACT,
    ESTAMP_CERTIFICATE_NUMBER,
    ESTAMP_DATE,
    GUARANTEE_FORM_NUM,
    GUARANTEE_FROM_DATE,
    GUARANTEE_TO_DATE,
    ISSUING_BRANCH_IFSC,
    ISSUING_BRANCH_NAME_ADDRESS,
    PLACE_OF_PAYMENT,
    PURPOSE_OF_GUARANTEE,
    RECEIVED_DATE,
    SENDER_TO_RECEIVER_INFO,
    SMSATEXT,
    STAMP_DUTY_PAID,
    STATE_CODE,
    TO_BE_HELD_IN_DEMAT,
    TYPE_OF_BG
)
VALUES (
    
    :AMOUNT_PAID,
    :APPLICANT_DETAILS,
    :ARTICLE_NUMBER,
    :BENEFICIARY_BANK_DETAILS,
    :BENEFICIARY_DETAILS,
    :BENEFICIARY_IFSC,
    :BG_AMOUNT,
    :BG_CURRENCY,
    :BG_EFFECTIVE_DATE,
    :BG_REF_NUM,
    :CLAIM_END_DATE,
    :CLAIM_LODGEMENT_PLACE,
    :CUSTODIAN_SERVICE_PROVIDER,
    :DATE_OF_PAYMENT,
    :DEMAT_ACCOUNT_NUM,
    :DESCRIPTION_OF_CONTRACT,
    :ESTAMP_CERTIFICATE_NUMBER,
    :ESTAMP_DATE,
    :GUARANTEE_FORM_NUM,
    :GUARANTEE_FROM_DATE,
    :GUARANTEE_TO_DATE,
    :ISSUING_BRANCH_IFSC,
    :ISSUING_BRANCH_NAME_ADDRESS,
    :PLACE_OF_PAYMENT,
    :PURPOSE_OF_GUARANTEE,
    :RECEIVED_DATE,
    :SENDER_TO_RECEIVER_INFO,
    :SMSATEXT,
    :STAMP_DUTY_PAID,
    :STATE_CODE,
    :TO_BE_HELD_IN_DEMAT,
    :TYPE_OF_BG
)
"""


# ============================================================
# AMENDMENT INSERT SQL
# ============================================================

INSERT_AMENDMENT_SQL = """
INSERT INTO EBG_AMENDMENTS_MJ (
    
    AMENDMENT_DATE,
    AMENDMENT_DETAILS,
    AMOUNT_PAID,
    APPLICANT_DETAILS,
    ARTICLE_NUMBER,
    BENEFICIARY_BANK_DETAILS,
    BENEFICIARY_DETAILS,
    BENEFICIARY_IFSC,
    BG_AMOUNT,
    BG_CLAIM_EXPIRY_DATE,
    BG_EXPIRY_DATE,
    BG_REF_NUM,
    CUSTODIAN_SERVICE_PROVIDER,
    DATE_OF_ISSUANCE,
    DATE_OF_PAYMENT,
    DEMAT_ACCOUNT_NUM,
    ESTAMP_CERTIFICATE_NUMBER,
    ESTAMP_DATE,
    ISSUING_BRANCH_IFSC,
    ISSUING_BRANCH_NAME_ADDRESS,
    NUM_OF_AMENDMENT,
    ORIGINAL_BG_NUM,
    PLACE_OF_PAYMENT,
    RECEIVED_DATE,
    REMARKS,
    SENDER_TO_RECEIVER_INFO,
    SMSATEXT,
    STAMP_DUTY_AMT_PAID,
    STAMP_DUTY_PAID,
    STATE_CODE,
    TO_BE_HELD_IN_DEMAT
)
VALUES (
    
    :AMENDMENT_DATE,
    :AMENDMENT_DETAILS,
    :AMOUNT_PAID,
    :APPLICANT_DETAILS,
    :ARTICLE_NUMBER,
    :BENEFICIARY_BANK_DETAILS,
    :BENEFICIARY_DETAILS,
    :BENEFICIARY_IFSC,
    :BG_AMOUNT,
    :BG_CLAIM_EXPIRY_DATE,
    :BG_EXPIRY_DATE,
    :BG_REF_NUM,
    :CUSTODIAN_SERVICE_PROVIDER,
    :DATE_OF_ISSUANCE,
    :DATE_OF_PAYMENT,
    :DEMAT_ACCOUNT_NUM,
    :ESTAMP_CERTIFICATE_NUMBER,
    :ESTAMP_DATE,
    :ISSUING_BRANCH_IFSC,
    :ISSUING_BRANCH_NAME_ADDRESS,
    :NUM_OF_AMENDMENT,
    :ORIGINAL_BG_NUM,
    :PLACE_OF_PAYMENT,
    :RECEIVED_DATE,
    :REMARKS,
    :SENDER_TO_RECEIVER_INFO,
    :SMSATEXT,
    :STAMP_DUTY_AMT_PAID,
    :STAMP_DUTY_PAID,
    :STATE_CODE,
    :TO_BE_HELD_IN_DEMAT
)
"""


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_next_id(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"SELECT NVL(MAX(ID),0)+1 FROM {table_name}")
    value = cur.fetchone()[0]
    cur.close()
    return value


def insert_issuance(conn, row):
    row["ID"] = get_next_id(conn, "EBG_ISSUANCES")

    params = {
        #"ID": row["ID"],
        "AMOUNT_PAID": row.get("amountPaid"),
        "APPLICANT_DETAILS": row.get("applicantDetails"),
        "ARTICLE_NUMBER": row.get("articleNumber"),
        "BENEFICIARY_BANK_DETAILS": row.get("beneficiaryBankDetails"),
        "BENEFICIARY_DETAILS": row.get("beneficiaryDetails"),
        "BENEFICIARY_IFSC": row.get("beneficiaryIFSC"),
        "BG_AMOUNT": row.get("bgAmount"),
        "BG_CURRENCY": row.get("bgCurrency"),
        "BG_EFFECTIVE_DATE": row.get("bgEffectiveDate"),
        "BG_REF_NUM": row.get("bgRefNum"),
        "CLAIM_END_DATE": row.get("claimEndDate"),
        "CLAIM_LODGEMENT_PLACE": row.get("claimLodgementPlace"),
        "CUSTODIAN_SERVICE_PROVIDER": row.get("custodianServiceProvider"),
        "DATE_OF_PAYMENT": row.get("dateOfPayment"),
        "DEMAT_ACCOUNT_NUM": row.get("dematAccountNum"),
        "DESCRIPTION_OF_CONTRACT": row.get("descriptionOfContract"),
        "ESTAMP_CERTIFICATE_NUMBER": row.get("estampCertificateNumber"),
        "ESTAMP_DATE": row.get("estampDate"),
        "GUARANTEE_FORM_NUM": row.get("guaranteeFormNum"),
        "GUARANTEE_FROM_DATE": row.get("guaranteeFromDate"),
        "GUARANTEE_TO_DATE": row.get("guaranteeToDate"),
        "ISSUING_BRANCH_IFSC": row.get("issuingBranchIFSC"),
        "ISSUING_BRANCH_NAME_ADDRESS": row.get("issuingBranchNameAddress"),
        "PLACE_OF_PAYMENT": row.get("placeOfPayment"),
        "PURPOSE_OF_GUARANTEE": row.get("purposeOfGuarantee"),
        "RECEIVED_DATE": row.get("receivedDate"),
        "SENDER_TO_RECEIVER_INFO": row.get("senderToReceiverInfo"),
        "SMSATEXT": row.get("smsatext"),
        "STAMP_DUTY_PAID": row.get("stampDutyPaid"),
        "STATE_CODE": row.get("stateCode"),
        "TO_BE_HELD_IN_DEMAT": row.get("toBeHeldInDemat"),
        "TYPE_OF_BG": row.get("typeOfBG"),
    }

    cur = conn.cursor()
    cur.execute(INSERT_ISSUANCE_SQL, params)
    cur.close()


def insert_amendment(conn, row):
    row["ID"] = get_next_id(conn, "EBG_AMENDMENTS")

    params = {
        #"ID": row["ID"],
        "AMENDMENT_DATE": row.get("amendmentDate"),
        "AMENDMENT_DETAILS": row.get("amendmentDetails"),
        "AMOUNT_PAID": row.get("amountPaid"),
        "APPLICANT_DETAILS": row.get("applicantDetails"),
        "ARTICLE_NUMBER": row.get("articleNumber"),
        "BENEFICIARY_BANK_DETAILS": row.get("beneficiaryBankDetails"),
        "BENEFICIARY_DETAILS": row.get("beneficiaryDetails"),
        "BENEFICIARY_IFSC": row.get("beneficiaryIFSC"),
        "BG_AMOUNT": row.get("bgAmount"),
        "BG_CLAIM_EXPIRY_DATE": row.get("bgClaimExpiryDate"),
        "BG_EXPIRY_DATE": row.get("bgExpiryDate"),
        "BG_REF_NUM": row.get("bgRefNum"),
        "CUSTODIAN_SERVICE_PROVIDER": row.get("custodianServiceProvider"),
        "DATE_OF_ISSUANCE": row.get("dateOfIssuance"),
        "DATE_OF_PAYMENT": row.get("dateOfPayment"),
        "DEMAT_ACCOUNT_NUM": row.get("dematAccountNum"),
        "ESTAMP_CERTIFICATE_NUMBER": row.get("estampCertificateNumber"),
        "ESTAMP_DATE": row.get("estampDate"),
        "ISSUING_BRANCH_IFSC": row.get("issuingBranchIFSC"),
        "ISSUING_BRANCH_NAME_ADDRESS": row.get("issuingBranchNameAddress"),
        "NUM_OF_AMENDMENT": row.get("numOfAmendment"),
        "ORIGINAL_BG_NUM": row.get("originalBGNum"),
        "PLACE_OF_PAYMENT": row.get("placeOfPayment"),
        "RECEIVED_DATE": row.get("receivedDate"),
        "REMARKS": row.get("remarks"),
        "SENDER_TO_RECEIVER_INFO": row.get("senderToReceiverInfo"),
        "SMSATEXT": row.get("smsatext"),
        "STAMP_DUTY_AMT_PAID": row.get("stampDutyAmtPaid"),
        "STAMP_DUTY_PAID": row.get("stampDutyPaid"),
        "STATE_CODE": row.get("stateCode"),
        "TO_BE_HELD_IN_DEMAT": row.get("toBeHeldInDemat"),
    }

    cur = conn.cursor()
    cur.execute(INSERT_AMENDMENT_SQL, params)
    cur.close()


def main():

    cfg = config.oracle

    conn = oracledb.connect(
        user=cfg.USER,
        password=cfg.PASSWORD,
        dsn=cfg.DSN,
        config_dir=cfg.CONFIG_DIR,
        wallet_location=cfg.WALLET_LOCATION,
        wallet_password=cfg.WALLET_PASSWORD,
    )

    json_path = sys.argv[1] if len(sys.argv) > 1 else r"F:\GMDC\gmdc_bg_api\database\json1.txt"

    payload = load_json(json_path)

    ebg_list = payload.get("data", {}).get("eBGList", {})

    issuances = ebg_list.get("eBGIssuanceList", [])
    amendments = ebg_list.get("eBGAmendList", [])

    issuance_count = 0
    amendment_count = 0

    for row in issuances:
        insert_issuance(conn, row)
        issuance_count += 1

    for row in amendments:
        insert_amendment(conn, row)
        amendment_count += 1

    conn.commit()

    print(f"Issuances Inserted : {issuance_count}")
    print(f"Amendments Inserted: {amendment_count}")

    conn.close()


if __name__ == "__main__":
    main()