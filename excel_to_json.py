from pathlib import Path

import pandas as pd


def excel_to_json(excel_path: Path) -> None:
    if not excel_path.exists():
        print(f"Không tìm thấy file: {excel_path}")
        return

    print(f"Đang đọc file Excel: {excel_path}")

    # Đọc tất cả các sheet vào dict {sheet_name: DataFrame}
    sheets = pd.read_excel(excel_path, sheet_name=None)

    for sheet_name, df in sheets.items():
        # Chuẩn hóa tên sheet cho an toàn khi làm tên file
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in str(sheet_name)
        )
        if not safe_name:
            safe_name = "sheet"

        out_path = excel_path.with_name(f"{safe_name}.json")
        print(f"-> Xuất sheet '{sheet_name}' -> {out_path.name}")

        df.to_json(out_path, orient="records", force_ascii=False, indent=2)

    print("Hoàn tất chuyển đổi tất cả sheet sang JSON.")


def main() -> None:
    # Mặc định lấy file DataBus.xlsx trong cùng thư mục script
    excel_path = Path(__file__).with_name("DataBus.xlsx")
    excel_to_json(excel_path)


if __name__ == "__main__":
    main()

