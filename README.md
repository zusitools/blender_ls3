blender_ls3
===========

Ein Blender-Plugin (Blender 2.80 und höher) für den Im- und Export von LS3-Dateien. Dieses XML-basierte Dateiformat wird von [Zusi 3](http://www.zusi.de) verwendet.

**Hinweis:** In der öffentlich verfügbaren Version werden keine Texturkoordinaten importiert.

**Installation und Bedienung:**

siehe [Dokumentation](http://zusitools.github.io/blender_ls3/)

**Note for English speaking people:** This add-on's translation is not affected by Blender's translation settings, as most German-speaking users will nevertheless use Blender in English. Due to the amount of technical terms, the add-on's default user interface language is German. However, if you use Zusi in English anyway (or if having German texts in an English user interface really bugs you for some reason), just delete or rename the `l10n` folder to switch the language to English.

**Unterschiede der Blender-2.8-Version**

Folgende Funktionen sind in der Version für Blender <= 2.79, aber nicht in der Version für Blender >= 2.80 verfügbar:
 - Einstellung, Import und Export von zBias
 - Einstellung, Import und Export von Alpha-Werten bei Farbangaben
 - Einstellung, Import und Export von "Meter pro Textur"
 - Objekte aus sichtbaren Ebenen exportieren (Blender 2.8 kennt keine Ebenen)
