"""Local visual-choice memory; advisory diversity without overriding musical fit."""
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import time


def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def medium_family(text):
    text=text.casefold()
    matches=[]
    for family,pattern in [('paper','paper|cutout|cut-out|collage'),('clay_puppet','clay|puppet|plasticine'),
        ('drawn','hand.drawn|cel.shad|2d|line animation'),('painted','paint|brush|watercolou?r|gouache'),
        ('three_dimensional','3d|three.dimensional|topology|subsurface'),('photographic','photograph|live.action|celluloid|filmic'),
        ('graphic','graphic|typograph|vector')]:
        for match in re.finditer(pattern,text):
            prefix=text[max(0,match.start()-28):match.start()]
            if re.search(r'\b(no|not|without|avoid)\b[^.;:]{0,24}$',prefix):continue
            matches.append((match.start(),family))
    return min(matches)[1] if matches else 'other'


def subject_family(text):
    text=text.casefold()
    # These labels are measurements of previous output, never positive examples
    # for the generator. Similarity also compares the full subject/environment.
    for family,pattern in [('watercraft',r'\b(boats?|sailboats?|ships?|skiffs?|rafts?|yachts?|canoes?|houseboats?)\b'),
        ('strands',r'\b(threads?|ribbons?|filaments?|filmstrips?)\b'),
        ('windows',r'\bwindows?\b'),('trees',r'\b(trees?|saplings?)\b'),
        ('human_figures',r'\b(figures?|persons?|people|woman|women|man|men|divers?|dancers?|characters?|puppets?)\b')]:
        if re.search(pattern,text): return family
    return 'other'


def tokens(text):
    ignored={'a','an','the','in','on','of','and','with','its','their','through','small','large','slow','soft','warm','glowing','gentle','subject','environment','title','treatment'}
    return {w for w in re.findall(r'[a-z]{3,}',text.casefold()) if w not in ignored}


def similarity(a,b):
    left=tokens(a); right=tokens(b)
    return len(left&right)/max(1,len(left|right))


MEDIA={'drawn':'Hand-drawn or line animation','painted':'Painted animation','three_dimensional':'Stylized 3D animation',
    'photographic':'Cinematic photographic or live-action imagery','clay_puppet':'Clay or puppet stop-motion',
    'paper':'Paper-based animation or collage','graphic':'Graphic motion design'}


def diversity_context(recent,seed):
    media=Counter(r['medium'] for r in recent); subjects=Counter(r['subject_family'] for r in recent if r['subject_family']!='other')
    choices=list(MEDIA); random.Random(seed).shuffle(choices)
    choices.sort(key=lambda name:media[name])
    limits=dict(title=80,subject=180,environment=120,motion_cycle=220,medium=40)
    return dict(recent_visual_choices=[{k:r[k][:limit] for k,limit in limits.items()} for r in recent[:6]],
        recent_medium_counts=dict(media),recent_subject_counts=dict(subjects),
        medium_options_less_recent_first=[MEDIA[k] for k in choices],
        instruction='Musical fit and explicit artist direction take priority. Seek fresh subject/story/medium combinations on unlocked dimensions. These records are previous outputs to compare against, not positive examples to imitate. Concept numbers have no permanent style assignment.')


def candidate_flags(concepts,recent):
    reports=[]; mediums=[medium_family(c['treatment']) for c in concepts]
    for index,c in enumerate(concepts,1):
        family=subject_family(c['subject']); medium=mediums[index-1]
        repeats=[r for r in recent if family!='other' and r['subject_family']==family]
        combo=[r for r in repeats if r['medium']==medium]
        overlap=max((similarity(c['subject']+' '+c['environment'],r['subject']+' '+r['environment']) for r in recent),default=0.)
        reports.append(dict(index=index,medium=medium,subject_family=family,recent_subject_uses=len(repeats),
            recent_combination_uses=len(combo),closest_subject_overlap=round(overlap,3),
            medium_shared_with_other_proposal=medium!='other' and mediums.count(medium)>1))
    return reports


def music_cues(evidence):
    values=[]; seen=set()
    if isinstance(evidence.get('summary'),str) and evidence['summary'].strip():
        values.append(dict(id='cue_01',kind='summary',observation=evidence['summary'][:1100]))
    for kind in ('style_tags','moods','instruments','production','vocals','tempo_bpm'):
        raw=evidence.get(kind); items=raw if isinstance(raw,list) else [raw]
        for item in items[:5]:
            if item is None or isinstance(item,(dict,list,bool)): continue
            value=str(item).strip()
            if not value or value.casefold() in seen: continue
            seen.add(value.casefold()); values.append(dict(id=f'cue_{len(values)+1:02d}',kind=kind,observation=value[:220]))
            if len(values)>=20: return values
    return values


class ConceptMemory:
    def __init__(self,user_directory,output_directory=None):
        root=Path(user_directory)/'MusicCanvas'; root.mkdir(parents=True,exist_ok=True)
        self.path=root/'concept_memory.sqlite3'
        with closing(self.connect()) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS selections (decision TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, title TEXT, subject TEXT, environment TEXT, motion_cycle TEXT, medium TEXT, subject_family TEXT, created REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS approach_selections (decision TEXT PRIMARY KEY, approach TEXT NOT NULL, created REAL NOT NULL)')
            seeded=db.execute("SELECT value FROM settings WHERE key='seeded'").fetchone()
            if not seeded:
                if output_directory:
                    files=sorted((Path(output_directory)/'music_canvas').glob('*/animation_brief.json'),key=lambda p:p.stat().st_mtime)[-120:]
                    for path in files:
                        try:
                            value=json.loads(path.read_text(encoding='utf-8')); concept=value['concept']
                            self.insert(db,'archive:'+digest(concept),concept,path.stat().st_mtime)
                        except (OSError,ValueError,KeyError,TypeError): continue
                db.execute("INSERT OR REPLACE INTO settings VALUES ('seeded','1')")

    def connect(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row; return db

    @staticmethod
    def insert(db,decision,c,created):
        if any(not isinstance(c.get(k),str) or not c[k].strip() for k in ('title','subject','environment','treatment')): return
        fingerprint=digest({k:c.get(k,'') for k in ('subject','environment','treatment','motion_cycle')})
        db.execute('INSERT INTO selections VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(decision) DO UPDATE SET medium=excluded.medium',
            (decision,fingerprint,c['title'][:160],c['subject'][:400],c['environment'][:220],c.get('motion_cycle','')[:650],medium_family(c['treatment']),subject_family(c['subject']),created))

    def recent(self,limit=24):
        with closing(self.connect()) as db:
            rows=db.execute('SELECT title,subject,environment,motion_cycle,medium,subject_family,MAX(created) AS last_selected FROM selections GROUP BY fingerprint ORDER BY last_selected DESC LIMIT ?', (limit,)).fetchall()
            return [dict(r) for r in rows]

    def remember(self,decision,concept):
        with closing(self.connect()) as db,db: self.insert(db,decision,concept,time.time())

    def remember_approach(self,decision,approach):
        with closing(self.connect()) as db,db:
            db.execute('INSERT OR IGNORE INTO approach_selections VALUES (?,?,?)',(decision,approach,time.time()))

    def approach_counts(self,limit=24):
        with closing(self.connect()) as db:
            rows=db.execute('SELECT approach FROM approach_selections ORDER BY created DESC LIMIT ?',(limit,)).fetchall()
            return dict(Counter(r['approach'] for r in rows))


REVIEW_SYSTEM='''You are the music-fit and concept-diversity editor for an animated music film. Return only the supplied JSON schema, with one review for each proposal index 1, 2, 3.
Musical fit comes FIRST. Check each rationale against the supplied evidence and cite its cue IDs. A visual interpretation need not literally depict the instruments or lyrics. Texture, phrasing, energy, production and emotional tension can justify an original story. Different subjects may fit the same song. Never invent musical facts, approved lyrics or artist biography. Do not require exact beat synchronization from a text prompt.
Then compare the proposals with each other and with recent selected concepts. Judge the subject, story premise, visible action and environment, not merely titles, palette or rendering medium. An old story repainted in another medium is still familiar. Repeated animation medium or a broad subject class alone is not a failed concept. Mark repeated only for substantially overlapping premise AND action, or a nearly identical subject/environment combination in the supplied records. Generic, simple or familiar does not mean repeated. An abstract animation need not become a conventional plot. Previous choices are comparison records, never subjects to imitate. Prefer an unexplored story combination when the artist leaves that dimension open.
Artist direction and exclusions are binding. Do not call a requested subject or medium a diversity problem; seek variety in the remaining dimensions. Do not replace a strong music interpretation with unrelated randomness. Quiet songs can have quiet but distinct stories.
Set music_fit=grounded only when the rationale has a defensible connection to supplied observations. Cite at least two distinct cue IDs when available, otherwise the one supplied. Set music_fit=weak for invented evidence, mismatched pacing/emotion, or a generic rationale without an actual connection.
Set novelty=fresh, familiar or repeated. Familiar is acceptable when the premise differs meaningfully; repeated means a substantially reused unlocked premise/action/subject combination or duplicate proposal. revision_needed=true only for weak music grounding or a repeated unlocked concept. Give actionable feedback under 35 words, naming dimensions to change rather than suggesting stock replacement subjects. Do not force literal instruments or scenes of music-making unless the artist requests them. Accept quiet or abstract imagery with a defensible musical connection. Do not demand novelty or a conventional plot for its own sake.'''
_review_fields=dict(index={'type':'integer','minimum':1,'maximum':3},
    music_fit={'type':'string','enum':['grounded','weak']},
    cue_ids={'type':'array','minItems':1,'maxItems':4,'items':{'type':'string'}},
    fit_reason={'type':'string','minLength':1,'maxLength':280},novelty={'type':'string','enum':['fresh','familiar','repeated']},
    revision_needed={'type':'boolean'},feedback={'type':'string','maxLength':320})
REVIEW_SCHEMA=dict(type='object',additionalProperties=False,required=['reviews'],properties=dict(reviews=dict(
    type='array',minItems=3,maxItems=3,items=dict(type='object',additionalProperties=False,required=list(_review_fields),properties=_review_fields))))


def validate_review(value,cues):
    if not isinstance(value,dict) or set(value)!={'reviews'} or not isinstance(value['reviews'],list) or len(value['reviews'])!=3:
        raise ValueError('Return exactly three concept reviews')
    allowed={c['id'] for c in cues}; required=min(2,len(allowed)); indices=[]
    for r in value['reviews']:
        if not isinstance(r,dict) or set(r)!=set(_review_fields): raise ValueError('Invalid concept review fields')
        index=r['index']; indices.append(index)
        if type(index) is not int or index not in (1,2,3): raise ValueError('Review indices must be 1, 2, 3')
        if r['music_fit'] not in ('grounded','weak') or r['novelty'] not in ('fresh','familiar','repeated') or type(r['revision_needed']) is not bool:
            raise ValueError('Invalid concept review decision')
        ids=r['cue_ids']
        if not isinstance(ids,list) or not all(isinstance(c,str) and c in allowed for c in ids):
            raise ValueError('Cite only the supplied musical cue IDs')
        if r['music_fit']=='grounded' and len(set(ids))<required: raise ValueError('Ground the rationale in distinct supplied musical cues')
        if not isinstance(r['fit_reason'],str) or not r['fit_reason'].strip() or not isinstance(r['feedback'],str): raise ValueError('Explain the review decision')
        # This flag is derived from the actual decisions, not another independent
        # model judgment. Normalize contradictions instead of crashing a valid
        # review over a redundant boolean.
        r['revision_needed']=r['music_fit']=='weak' or r['novelty']=='repeated'
        if r['revision_needed'] and not r['feedback'].strip():
            r['feedback']=('Ground the rationale and physical pacing in the supplied musical observations without inventing evidence.'
                if r['music_fit']=='weak' else 'Change the unlocked premise and physical action while preserving musical fit and artist direction.')
    if sorted(indices)!=[1,2,3]: raise ValueError('Review each concept exactly once')
    return value
