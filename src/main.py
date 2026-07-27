from universal_hardening import install_universal_hardening

install_universal_hardening()

from enhanced_reporting import install_reporting_enhancements

install_reporting_enhancements()

import app
from quality_control import compare_modal_datasets_with_quality_control
from runtime_hardening import install_runtime_hardening
from ui_enhancements import install_app_enhancements

# Bind the reviewed comparison path explicitly. No import-order monkey patch is required.
app.compare_modal_datasets = compare_modal_datasets_with_quality_control
install_app_enhancements(app)
install_runtime_hardening(app)


if __name__ == "__main__":
    app.main()
