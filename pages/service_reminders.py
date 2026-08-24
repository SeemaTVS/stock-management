import datetime
from datetime import timedelta
import pandas as pd
import streamlit as st

st.title("TVS Agency Service Reminder Portal")


@st.cache_resource
def get_conn():
  # Uses Streamlit's native gsheets connection
  return st.connection("gsheets", type="gsheets")


def load_data():
  try:
    conn = get_conn()
    df = conn.read(
        spreadsheet="1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM",
        worksheet="Service_Reminders",
        ttl=0,
    )
    if df.empty or "Name" not in df.columns:
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
    return df
  except Exception:
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


def save_new_row(new_data_dict):
  conn = get_conn()
  existing_df = load_data()
  updated_df = pd.concat(
      [existing_df, pd.DataFrame([new_data_dict])], ignore_index=True
  )
  conn.update(
      spreadsheet="1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM",
      worksheet="Service_Reminders",
      data=updated_df,
  )


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

        row_data = {
            "Name": name,
            "Phone": str(phone),
            "Bike": bike,
            "Free_Services_Count": int(free_services_count),
            "Purchase_Date": str(purchase_date),
            "Current_Service_Stage": stage,
            "Next_Due_Date": str(next_due),
            "Status": "Pending",
        }

        save_new_row(row_data)
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

              df.at[index, "Current_Service_Stage"] = next_stage
              df.at[index, "Next_Due_Date"] = str(next_due_calc)
              df.at[index, "Status"] = "Pending"

              conn = get_conn()
              conn.update(
                  spreadsheet="1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM",
                  worksheet="Service_Reminders",
                  data=df,
              )

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
