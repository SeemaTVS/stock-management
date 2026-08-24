import datetime
from datetime import timedelta
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st

st.title("TVS Agency Service Reminder Portal")


@st.cache_resource
def get_worksheet():
  scope = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  # Uses Streamlit secrets for Google Cloud credentials
  creds_dict = dict(st.secrets["connections"]["gsheets"])
  creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
  client = gspread.authorize(creds)
  sheet = client.open_by_key(
      "1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM"
  )
  try:
    return sheet.worksheet("Service_Reminders")
  except gspread.exceptions.WorksheetNotFound:
    ws = sheet.add_worksheet(title="Service_Reminders", rows="1000", cols="8")
    ws.append_row([
        "Name",
        "Phone",
        "Bike",
        "Free_Services_Count",
        "Purchase_Date",
        "Current_Service_Stage",
        "Next_Due_Date",
        "Status",
    ])
    return ws


worksheet = get_worksheet()


def load_data():
  data = worksheet.get_all_records()
  if not data:
    return pd.DataFrame(columns=[
        "Name",
        "Phone",
        "Bike",
        "Free_Services_Count",
        "Purchase_Date",
        "Current_Service_Stage",
        "Next_Due_Date",
        "Status",
    ])
  return pd.DataFrame(data)


df = load_data()

menu = st.selectbox(
    "Choose Action", ["View Due Reminders", "Add New Customer", "All Records"]
)

if menu == "Add New Customer":
  st.subheader("Add Customer for Automated Service Scheduling")
  with st.form("reminder_form"):
    name = st.text_input("Customer Name")
    phone = st.text_input("Phone Number")
    bike = st.text_input("Bike Model")
    purchase_date = st.date_input(
        "Purchase Date / Last Service Date", datetime.date.today()
    )
    free_services_count = st.selectbox(
        "Number of Free Services for this Vehicle",
        [3, 4],
        format_func=lambda x: f"{x} Free Services",
    )

    submitted = st.form_submit_button("Save Customer & Schedule")
    if submitted:
      if name and phone:
        next_due = purchase_date + timedelta(days=60)
        stage = "1st Service (Free)"

        row_data = [
            name,
            str(phone),
            bike,
            int(free_services_count),
            str(purchase_date),
            stage,
            str(next_due),
            "Pending",
        ]

        worksheet.append_row(row_data)
        st.success(
            f"Customer {name} saved to Google Sheets! Scheduled for {stage} on"
            f" {next_due.strftime('%d-%m-%Y')}."
        )
      else:
        st.error("Please fill in at least the customer name and phone number.")

elif menu == "View Due Reminders":
  st.subheader("Service Calls Due Today & Overdue")
  df = load_data()
  if not df.empty and "Next_Due_Date" in df.columns:
    today = str(datetime.date.today())
    due_filter = (df["Next_Due_Date"] <= today) & (df["Status"] == "Pending")
    due_df = df[due_filter]

    if not due_df.empty:
      st.write(f"You have {len(due_df)} customer calls pending:")
      for index, row in due_df.iterrows():
        with st.expander(
            f"{row['Name']} - {row['Bike']} ({row['Current_Service_Stage']} - Due:"
            f" {row['Next_Due_Date']})"
        ):
          st.write(f"**Phone Number:** {row['Phone']}")
          st.write(f"**Free Services Scheme:** {row['Free_Services_Count']} Services")

          col1, col2 = st.columns(2)
          with col1:
            if st.button(
                f"Mark as Called & Advance Schedule", key=f"call_{index}"
            ):
              sheet_row_idx = (
                  index + 2
              )  # Account for 1-based indexing + header row
              current_stage = row["Current_Service_Stage"]
              free_limit = int(row["Free_Services_Count"])
              base_date = datetime.date.today()

              next_stage = current_stage
              next_due_calc = base_date + timedelta(days=180)

              if free_limit == 4:
                if "1st" in current_stage:
                  next_stage = "2nd Service (Free)"
                  next_due_calc = base_date + timedelta(days=120)
                elif "2nd" in current_stage:
                  next_stage = "3rd Service (Free)"
                  next_due_calc = base_date + timedelta(days=240)
                elif "3rd" in current_stage:
                  next_stage = "4th Service (Free)"
                  next_due_calc = base_date + timedelta(days=365)
                else:
                  next_stage = "Subsequent Service (Paid)"
                  next_due_calc = base_date + timedelta(days=90)
              else:
                if "1st" in current_stage:
                  next_stage = "2nd Service (Free)"
                  next_due_calc = base_date + timedelta(days=180)
                elif "2nd" in current_stage:
                  next_stage = "3rd Service (Free)"
                  next_due_calc = base_date + timedelta(days=365)
                elif "3rd" in current_stage:
                  next_stage = "4th Service (Paid)"
                  next_due_calc = base_date + timedelta(days=548)
                else:
                  next_stage = "Subsequent Service (Paid)"
                  next_due_calc = base_date + timedelta(days=180)

              worksheet.update_cell(sheet_row_idx, 6, next_stage)
              worksheet.update_cell(sheet_row_idx, 7, str(next_due_calc))
              worksheet.update_cell(sheet_row_idx, 8, "Pending")

              st.success(
                  f"Call logged. Next schedule updated to {next_stage} on"
                  f" {next_due_calc}."
              )
              st.rerun()

          with col2:
            whatsapp_link = (
                f"https://wa.me/91{row['Phone']}?text=Hello%20{row['Name']},%20this"
                f"%20is%20from%20TVS%20agency.%20Your%20{row['Bike']}%20is"
                f"%20due%20for%20{row['Current_Service_Stage']}."
            )
            st.markdown(f"[Open WhatsApp Chat]({whatsapp_link})")
    else:
      st.info("No service calls due right now.")
  else:
    st.info("No customer records found yet.")

elif menu == "All Records":
  st.subheader("Complete Customer Service Database")
  df = load_data()
  if not df.empty:
    st.dataframe(df, use_container_width=True)
  else:
    st.info("No records available.")
