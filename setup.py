from setuptools import setup, find_packages

setup(
    name="ingar",
    version="1.0.0",
    description="Software de acceso remoto - Similar a TeamViewer",
    author="Ingar Project",
    packages=find_packages(),
    install_requires=[
        "websockets>=12.0",
        "mss>=9.0",
        "Pillow>=10.0",
        "pynput>=1.7",
        "cryptography>=42.0",
    ],
    entry_points={
        "console_scripts": [
            "ingar-server=server.signaling_server:main_sync",
            "ingar=client.main:main",
        ],
    },
    python_requires=">=3.8",
)
