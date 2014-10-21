blender_ls3
===========

Ein Blender-Plugin für den Im- und Export von .ls3-Dateien. Dieses XML-basierte Dateiformat wird von [Zusi 3](http://www.zusi.de) verwendet.

**Installation:** 

 * Es wird Blender-Version 2.63a oder höher vorausgesetzt.
 * [Release als ZIP herunterladen](https://github.com/zusitools/blender_ls3/releases) oder aktuellen Repository-Stand via Git herunterladen.
 * Unter Linux: Gemäß der Anleitung in `zusiconfig.py.default` den Pfad zum Zusi-Datenverzeichnis sowie optional die Autoreninfo eintragen
 * Den Ordner `io_scene_ls3` aus der ZIP-Datei mitsamt den enthaltenen Dateien in den Unterordner `<version>/scripts/addons` des Blender-Programmverzeichnisses kopieren. `<version>` ist die Versionsnummer von Blender, etwa *2.63*.
     * Alternativ kann auch in den Blender-Einstellungen unter `File` ein Pfad zu benutzerdefinierten Skriptdateien („Scripts“) angegeben werden. In diesem Verzeichnis muss dann ein Unterverzeichnis `addons` existieren, in das der Ordner `io_scene_ls3` kopiert werden muss.
 * In Blender:
     * Neue leere Datei öffnen (`Strg+N`)
     * File → User Preferences
     * Reiter „Add-ons“ wählen
     * In das Suchfeld „Zusi“ eingeben und beim erscheinenden Add-on „Import-Export: Zusi Scenery Format (.ls3)“ das Ankreuzkästchen aktivieren.
     * „Save Defaults“

Der Import ist erreichbar über File → Import → Zusi-Landschaft (.ls3) oder über *Leertaste* → LS3 importieren.

Der Import ist erreichbar über File → Export → Zusi-Landschaft (.ls3) oder über *Leertaste* → LS3 exportieren.

**Hinweis:** In der öffentlich verfügbaren Version wird das binäre Format von Zusi 3 (.lsb) nicht gelesen oder geschrieben und es werden keine Texturkoordinaten importiert.

**Note for English speaking people:** This add-on's translation is not affected by Blender's translation settings, as most German-speaking users will nevertheless use Blender in English. Due to the amount of technical terms, the add-on's default user interface language is German. However, if you use Zusi in English anyway (or if having German texts in an English user interface really bugs you for some reason), just delete or rename the `l10n` folder to switch the language to English.
