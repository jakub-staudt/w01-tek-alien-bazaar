from setuptools import setup

package_name = "wojtek_spectacles_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Jakub Staudt",
    maintainer_email="kubastaudt@gmail.com",
    description="Snap Spectacles pinch-drag joystick -> /cmd_vel bridge for wojtek.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "spectacles_bridge = wojtek_spectacles_bridge.spectacles_bridge:main",
        ],
    },
)
