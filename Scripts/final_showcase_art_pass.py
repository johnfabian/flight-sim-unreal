import runpy
from pathlib import Path
import unreal
scripts=Path(unreal.Paths.project_dir()).resolve()/'Scripts'
runpy.run_path(str(scripts/'finish_showcase_atmosphere.py'))
runpy.run_path(str(scripts/'enrich_showcase_forest.py'))
