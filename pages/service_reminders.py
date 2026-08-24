import datetime
from datetime import timedelta
import pandas as pd
import requests
import streamlit as st

st.title("TVS Agency Service Reminder Portal")

# Google Sheet and Web App endpoints
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM/edit?gid=0#gid=0"
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbymkbPavkWPw_5kFEN7S6KQTg2MvS_zqAmGXXkqBAjVDo7XrnUCj9GKKKrA_heBvWZvmQ/exec"


def get_csv_export_url(sheet_url, sheet_name="Service_Reminders"):
  import re

  match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
  if match:
    return (
        f"https://docs.google.com/spreadsheets/d/{match.group(1)}/gviz/tq?"
        f"tqx=out:csv&sheet={sheet_name}"
    )
  return sheet_url


EXPECTED_COLS = [
    "Name",
    "Phone",
    "Bike",
    "Free_Services_Count",
    "Latest_Service_Date",
    "Current_Service_Stage",
    "Next_Due_Date",
    "Status",
]


@st.cache_data(ttl=10)
def load_data():
  try:
    csv_url = get_csv_export_url(GOOGLE_SHEET_URL, "Service_Reminders")
    df_loaded = pd.read_csv(csv_url)
    for col in EXPECTED_COLS:
      if col not in df_loaded.columns:
        df_loaded[col] = ""
    df_loaded["Status"] = df_loaded["Status"].fillna("Pending")
    return df_loaded
  except Exception as e:
    st.warning(
        "Could not load Service_Reminders tab from Google Sheet yet. Details:"
        f" {e}"
    )
    return pd.DataFrame(columns=EXPECTED_COLS)


def save_data_to_cloud(df_to_save):
  try:
    if WEB_APP_URL:
      records = df_to_save[EXPECTED_COLS].to_dict(orient="records")
      payload = {"type": "service_reminders", "data": records}
      response = requests.post(WEB_APP_URL, json=payload, timeout=10)
      if response.status_code == 200:
        st.success("Changes synced to Google Sheets!")
      else:
        st.error(f"Sync failed with status code: {response.status_code}")
  except Exception as e:
    st.error(f"Error syncing to cloud: {e}")


df = load_data()

# Sidebar: Customer Management (Adding new customers)
st.sidebar.header("Customer Management")
with st.sidebar.form("add_customer_form"):
  st.subheader("Register New Vehicle")
  name = st.text_input("Customer Name")
  phone = st.text_input("Phone Number")
  bike = st.text_input("Bike Model")
  purchase_date = st.date_input("Purchase Date", datetime.date.today())
  free_services_count = st.selectbox(
      "Free Services Scheme", [3, 4], format_func=lambda x: f"{x} Free Services"
  )

  submitted = st.form_submit_button("Save Customer")
  if submitted:
    if name and phone:
      next_due = purchase_date + timedelta(days=60)
      stage = "1st Service (Free)"

      new_row = pd.DataFrame([{
          "Name": name.strip(),
          "Phone": str(phone).strip(),
          "Bike": bike.strip(),
          "Free_Services_Count": int(free_services_count),
          "Latest_Service_Date": str(purchase_date),
          "Current_Service_Stage": stage,
          "Next_Due_Date": str(next_due),
          "Status": "Pending",
      }])

      updated_df = pd.concat([df, new_row], ignore_index=True)
      save_data_to_cloud(updated_df)
      st.sidebar.success(f"Customer {name} added successfully!")
      st.rerun()
    else:
      st.sidebar.error("Please enter Name and Phone.")

# Main screen view toggle: Interactive button for reminders vs all records
if "view_mode" not in st.session_state:
  st.session_state["view_mode"] = "All Records"

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
  if st.button("🔔 View Due Reminders", use_container_width=True):
    st.session_state["view_mode"] = "Reminders"
with col_btn2:
  if st.button("📋 All Records", use_container_width=True):
    st.session_state["view_mode"] = "All Records"

st.markdown("---")

# Render based on selected main view mode
if st.session_state["view_mode"] == "Reminders":
  st.subheader("Service Pipeline & Reminders")
  if not df.empty and "Next_Due_Date" in df.columns:
    today = str(datetime.date.today())
    active_filter = (df["Next_Due_Date"] <= today) & (
        df["Status"].isin(["Pending", "Called"])
    )
    active_df = df[active_filter]

    if not active_df.empty:
      st.write(f"You have **{len(active_df)}** active service reminders:")

      for index, row in active_df.iterrows():
        current_status = str(row.get("Status", "Pending"))

        if current_status == "Called":
          border_color = "#FF9800"  # Orange
          status_badge = "🟠 Called - Service Pending"
        else:
          border_color = "#F44336"  # Red
          status_badge = "🔴 Due - Not Called Yet"

        st.markdown(
            f"""
            <div style="border: 2px solid {border_color}; padding: 10px; border-radius: 6px; margin-bottom: 5px; background-color: #fafafa;">
                <h4 style="margin: 0; color: #333;">{row['Name']} - {row['Bike']}</h4>
                <p style="margin: 3px 0; font-size: 13px;"><b>Status:</b> {status_badge}</p>
                <p style="margin: 3px 0; font-size: 13px;"><b>Milestone:</b> {row['Current_Service_Stage']} | <b>Due:</b> {row['Next_Due_Date']}</p>
                <p style="margin: 3px 0; font-size: 13px;"><b>Phone:</b> {row['Phone']} | <b>Last Date:</b> {row['Latest_Service_Date']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_f1, col_f2, col_f3 = st.columns(3)

        with col_f1:
          st.markdown(
              f'<a href="tel:{row["Phone"]}" target="_self"><button'
              ' style="width:100%;background-color:#4CAF50;color:white;border:none;padding:8px;border-radius:4px;cursor:pointer;">📞'
              " Call Now</button></a>",
              unsafe_allow_html=True,
          )

        with col_f2:
          if st.button("📢 Mark as Called", key=f"call_click_{index}"):
            df.loc[index, "Status"] = "Called"
            save_data_to_cloud(df)
            st.success(f"Updated {row['Name']} to Called!")
            st.rerun()

        with col_f3:
          if st.button("✅ Service Completed", key=f"complete_click_{index}"):
            current_stage = str(row["Current_Service_Stage"])
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

            df.loc[index, "Current_Service_Stage"] = next_stage
            df.loc[index, "Latest_Service_Date"] = str(base_date)
            df.loc[index, "Next_Due_Date"] = str(next_due_calc)
            df.loc[index, "Status"] = "Completed"

            save_data_to_cloud(df)
            st.success(
                f"Service completed for {row['Name']}! Next milestone:"
                f" {next_due_calc}."
            )
            st.rerun()
    else:
      st.info("No active service calls due right now.")
  else:
    st.info("No customer records found.")

else:
  st.subheader("Complete Customer Service Database")
  if not df.empty:
    st.dataframe(df, use_container_width=True)
  else:
    st.info("No records found.")
