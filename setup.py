from setuptools import setup, find_packages

setup(
    name="voice-ai-studio-arabic",
    version="2.0.0",
    description="منصة صوتيات عربية لتوليد واستنساخ الصوت",
    packages=find_packages(),
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "voice-ai=main:app",
        ],
    },
)
