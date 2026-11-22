# Receipt scanning uses only ML Kit's Latin-script recogniser; the plugin
# also references the Chinese, Devanagari, Japanese and Korean models, which
# are not bundled. Tell R8 not to expect them.
-dontwarn com.google.mlkit.vision.text.chinese.**
-dontwarn com.google.mlkit.vision.text.devanagari.**
-dontwarn com.google.mlkit.vision.text.japanese.**
-dontwarn com.google.mlkit.vision.text.korean.**
