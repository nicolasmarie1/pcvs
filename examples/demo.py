from pcvs.dsl import Bank
from pcvs.dsl import Job
from pcvs.dsl import Run
from pcvs.dsl import Series

# open a bank
bank = Bank("./demo.git")

# retrieve project/configs within the bank
# a given series is identified by:
# - a name
# - a hash, based on a specific profile
list_of_projects = bank.list_projects()
configs_for_project = bank.list_series(list_of_projects[0])
series = bank.get_series(configs_for_project[0])

# Modifiers
job_list = series.find(Series.Request.REGRESSIONS, since=None, until=None)

# Create a run to edit
run = Run(series)

# mark each failed jobs as success
for job in job_list:
    job.status = Job.State.SUCCESS
    run.update(job.name, job)

# save the run as the last one for this series
series.commit(run)
