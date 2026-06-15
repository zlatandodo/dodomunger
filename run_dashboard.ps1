# Launch the Weekly Munger Scanner dashboard.
# Usage:  ./run_dashboard.ps1
Set-Location -Path $PSScriptRoot
python -m streamlit run app.py
