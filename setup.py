from setuptools import setup, find_packages

setup(
    name="voice-ai-studio-arabic",
    version="6.0.0",
    description="منصة صوتيات عربية لتوليد واستنساخ الصوت",
    packages=find_packages(),
    python_requires=">=3.9,<3.14",
    entry_points={
        "console_scripts": [
            "voice-ai=main:app",
        ],
    },
)
