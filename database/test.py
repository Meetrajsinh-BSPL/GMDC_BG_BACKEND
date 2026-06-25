import oracledb
from config.config import config


def main():
    cfg = config.oracle

    try:
        conn = oracledb.connect(
            user=cfg.USER,
            password=cfg.PASSWORD,
            dsn=cfg.DSN,
            config_dir=cfg.CONFIG_DIR,
            wallet_location=cfg.WALLET_LOCATION,
            wallet_password=cfg.WALLET_PASSWORD,
        )

        cursor = conn.cursor()

        cursor.execute("SELECT * FROM ebg_requests FETCH FIRST 1 ROWS ONLY")

        # ✅ Get column names
        columns = [col[0] for col in cursor.description]

        # ✅ Get one row
        result = cursor.fetchone()

        print("✅ Oracle Connection Successful")
        print("Columns:", columns)
        print("Test Query Result:", result)

        cursor.close()
        conn.clos

    except Exception as e:
        print("❌ Oracle Connection Failed")
        print("Error:", str(e))


if __name__ == "__main__":
    main()