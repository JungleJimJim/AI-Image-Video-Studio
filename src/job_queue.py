"""Persistent serial job ordering. Does not load models or execute media jobs."""
from copy import deepcopy
from pathlib import Path
import secrets
import time

from common import atomic_json, load_json

ACTIVE = ('queued', 'running')
KINDS = ('image', 'video', 'edit', 'enhance_image', 'enhance_video', 'avatar','faceswap','faceswap_video','voice')


class JobQueue:
    def __init__(self, root):
        self.path = Path(root) / 'queue.json'
        data = load_json(self.path, {})
        self.jobs = data.get('jobs', []) if isinstance(data, dict) else []
        self.paused = bool(data.get('paused', False)) if isinstance(data, dict) else False
        self.continue_on_error = bool(data.get('continue_on_error', True)) if isinstance(data, dict) else True
        for job in self.jobs:
            if job.get('status') == 'running':
                job.update(status='interrupted', error='The app closed during this job. Review and retry it.')
        # Never resume inference unattended after reopening the app.
        if any(x.get('status') == 'queued' for x in self.jobs):
            self.paused = True

    def save(self):
        finished=[x for x in self.jobs if x['status'] not in ACTIVE]
        if len(finished)>100:
            keep={x['id'] for x in finished[-100:]}
            self.jobs=[x for x in self.jobs if x['status'] in ACTIVE or x['id'] in keep]
        atomic_json(self.path, dict(paused=self.paused, continue_on_error=self.continue_on_error, jobs=self.jobs))

    @staticmethod
    def priority(value):
        try:
            n = float(value)
            if not n.is_integer() or not 0 <= n <= 10:
                raise ValueError()
            return int(n)
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Priority must be a whole number from 0 to 10.') from None

    def get(self, identifier):
        job = next((x for x in self.jobs if x['id'] == identifier), None)
        if not job:
            raise ValueError('Queue job not found.')
        return job

    def add(self, kind, options, priority=5, output=''):
        if kind not in KINDS:
            raise ValueError('Unknown queue job type.')
        if sum(x['status'] in ACTIVE for x in self.jobs) >= 100:
            raise ValueError('The queue supports up to 100 unfinished jobs.')
        job = dict(id=secrets.token_hex(12), kind=kind, options=deepcopy(options), output=output,
                   priority=self.priority(priority), order=max((x['order'] for x in self.jobs), default=0)+1,
                   status='queued', created=time.strftime('%Y-%m-%d %H:%M:%S'), error='')
        self.jobs.append(job)
        self.save()
        return job

    def pending(self):
        return sorted((x for x in self.jobs if x['status']=='queued'), key=lambda x:(-x['priority'],x['order']))

    def next(self):
        return None if self.paused else next(iter(self.pending()), None)

    def update(self, identifier, options=None, priority=None):
        job = self.get(identifier)
        if job['status'] != 'queued':
            raise ValueError('Only waiting jobs can be edited. Retry a finished job to make a new copy.')
        if priority is not None:
            job['priority'] = self.priority(priority)
        if options is not None:
            job['options'] = deepcopy(options)
        self.save()
        return job

    def move(self, identifier, direction):
        job = self.get(identifier)
        if job['status'] != 'queued' or direction not in ('up','down'):
            raise ValueError('Choose a waiting job and move up or down.')
        peers = [x for x in self.pending() if x['priority']==job['priority']]
        index = peers.index(job)
        other = index + (-1 if direction=='up' else 1)
        if 0 <= other < len(peers):
            job['order'], peers[other]['order'] = peers[other]['order'], job['order']
            self.save()

    def snapshot(self):
        running = [x for x in self.jobs if x['status']=='running']
        finished = [x for x in reversed(self.jobs) if x['status'] not in ACTIVE][:100]
        jobs = running + self.pending() + finished
        return dict(paused=self.paused, continue_on_error=self.continue_on_error, waiting=len(self.pending()),
                    jobs=[{k:deepcopy(v) for k,v in x.items() if k!='options'} |
                          dict(model=x['options'].get('model',''), prompt=x['options'].get('prompt',x['options'].get('text','')),
                               width=x['options'].get('width'),height=x['options'].get('height')) for x in jobs])
