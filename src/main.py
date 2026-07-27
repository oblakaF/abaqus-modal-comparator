from quality_control import install_quality_control
from enhanced_reporting import install_reporting_enhancements

install_quality_control()
install_reporting_enhancements()

import app
from ui_enhancements import install_app_enhancements

install_app_enhancements(app)


if __name__ == "__main__":
    app.main()
