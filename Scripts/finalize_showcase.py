"""One-time integration of the reviewed lighting region and atmosphere."""
import runpy,unreal
from pathlib import Path
scripts=Path(unreal.Paths.project_dir()).resolve()/'Scripts'
runpy.run_path(str(scripts/'tune_showcase_lighting.py'))
runpy.run_path(str(scripts/'finish_showcase_atmosphere.py'))
