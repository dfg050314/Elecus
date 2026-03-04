import ecs_route
from pyrevit import script as pr_script

out = pr_script.get_output()
out.print_md("ecs_route dir: {}".format(dir(ecs_route)))