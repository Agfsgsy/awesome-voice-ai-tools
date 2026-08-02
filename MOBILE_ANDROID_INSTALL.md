# تثبيت وبناء تطبيق Android

## المتطلبات

1. ثبّت Flutter من القناة `stable` وأضف `flutter/bin` إلى `PATH`.
2. ثبّت Android Studio، ثم من SDK Manager ثبّت Android SDK وPlatform Tools وBuild Tools.
3. ثبّت JDK 17.
4. اقبل تراخيص Android:

```bash
flutter doctor --android-licenses
flutter doctor -v
```

التطبيق يستهدف Android 10 / API 29 فأحدث.

بعد أول تشغيل لا يلزم كمبيوتر: افتح الإعدادات لتثبيت بيانات الصوت العربي المحلية، وأدخل مفاتيح Gemini أو ElevenLabs الخاصة بك إن أردت الأدوات السحابية المباشرة. المفاتيح لا تأتي داخل APK وتُحفظ في Android Keystore.

## وضع التطوير

```bash
cd mobile_app
flutter pub get
flutter analyze --fatal-infos
flutter test
flutter run
```

فعّل USB debugging على الهاتف وتحقق منه بواسطة `adb devices`، أو اختر محاكيًا من Android Studio.

## بناء APK

Windows:

```bat
BUILD_ANDROID_APK.bat
```

Linux:

```bash
./build_android_apk.sh
```

تُنسخ النتيجة وملف SHA-256 إلى `dist/mobile/android/`. لبناء نسخة Debug موقعة تلقائيًا بمفتاح Android التجريبي وقابلة للتثبيت مباشرة:

```bash
python scripts/build_android_app.py --apk --debug
```

## بناء AAB

Windows:

```bat
BUILD_ANDROID_AAB.bat
```

Linux:

```bash
./build_android_aab.sh
```

ملف AAB مخصص للنشر في Google Play ولا يُثبت مباشرة بواسطة `adb`.

## توقيع Release

لا يحتوي المستودع أي مفتاح توقيع. أنشئ مفتاحًا محليًا خارج Git، ثم أنشئ `mobile_app/android/key.properties` محليًا بالقيم التالية:

```properties
storePassword=YOUR_STORE_PASSWORD
keyPassword=YOUR_KEY_PASSWORD
keyAlias=YOUR_ALIAS
storeFile=/absolute/private/path/upload-keystore.jks
```

الملف ومسارات keystore مستثناة من Git. في GitHub Actions استخدم الأسرار:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`
- `ANDROID_STORE_PASSWORD`

إذا لم تتوفر الأسرار، ينتج CI ملفات Release غير موقعة للمراجعة. استخدم Build Debug للتثبيت التجريبي، أو وقّع Release محليًا قبل التثبيت.

## تثبيت APK على الهاتف

لهواتف Android الحديثة بمعمارية ARM64 استخدم الملف
`voice-ai-studio-android-arm64-v1.2.1-build4.apk`. حجمه أصغر من APK الشامل،
ويُنشر في GitHub Releases برابط تنزيل مباشر حتى لا يعتمد المستخدم على روابط
المحادثة المؤقتة. يبنى هذا الملف بوضع Release المحسن، ويُوقّع بمفتاح Release
عند توفر أسرار التوقيع أو بمفتاح Android التجريبي ليكون قابلًا للتثبيت عند
غيابها. لا تستخدم ملف AAB للتثبيت المباشر.

1. وصّل الهاتف وفعّل USB debugging.
2. ابنِ نسخة Debug القابلة للتثبيت.
3. نفّذ:

```bash
adb install -r dist/mobile/android/voice-ai-mobile-debug.apk
```

بديلًا، انسخ APK الموقع إلى الهاتف وافتحه من تطبيق الملفات، ثم اسمح بالتثبيت من ذلك المصدر عند طلب Android.
