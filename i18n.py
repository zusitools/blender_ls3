import gettext
import inspect
import os

script_path = os.path.dirname(inspect.getfile(inspect.currentframe()))
l10n_path = os.path.join(script_path, 'l10n')
language = gettext.translation('blender_ls3', l10n_path, languages=['de'], fallback=True)
print(language)
