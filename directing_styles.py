"""Music-grounded directing options with independent medium locks."""
import copy
import random

APPROACHES={
    'Character journey':'A protagonist actively pursues a concrete goal, encounters resistance and changes the situation through its own action; being carried or floating without purpose is insufficient.',
    'Choreographed world':'At least two objects, architectural or landscape elements interact through patterned choreography shaped by the groove; the surrounding world performs, not just a lone dancing figure.',
    'Visual transformation':'Forms and materials evolve through connected transformations with lasting visible consequences.',
    'Cinematic observation':'Purposeful gestures, composition and changes in atmosphere carry emotion and reveal new information.',
    'Surreal narrative':'An impossible but consistent visual rule triggers a sequence of consequences and a concrete payoff; a lone floating object is insufficient.',
    'Associative montage':'Connect at least two distinct images, subjects or environments through a match cut in shape, motion or colour. Show the actual cuts; a character moving around one place is insufficient.',
    'Performance-led':'Expressive dance or physical performance develops through changing phrases, staging and interaction.',
    'Escalating spectacle':'Scale, choreography and editing develop toward musical intensity; escalation can remain restrained for quiet music.'}
MEDIA=['Hand-drawn or line animation','Painted animation','Stylized 3D animation',
       'Cinematic photographic or live-action imagery','Clay or puppet stop-motion',
       'Paper-based animation or collage','Graphic motion design']

SLATE_SYSTEM='''You are a music-film creative director. Choose the requested number of approaches for the supplied song, artist direction and exclusions. Directing approach is independent of animation medium. Return only the requested JSON.
First write music_direction using ONLY pacing, movement dynamics, emotional tension, rhythmic phrasing and surface/texture qualities inferred from the music. Do not prescribe subjects, props, settings, specific materials, palette colours or animation media in that shared brief. Those choices must differ between candidate premises. Keep it under 90 words, as complete sentences. Preserve uncertainty; never invent sound facts, lyrics or exact synchronization. A quiet song can have flowing expressive action and quiet progression.
When directing_approach is none, choose DISTINCT approaches from the menu that fit this music. Give Performance-led and Choreographed world priority when a clear groove or a request for dance calls for them. When locked, use the requested approach for every proposal. Build each premise around a subject, setting, and visible movement phrase that develops. A new gesture, spatial pattern or interaction can be the entire arc. Leave out backstory and symbols that add no movement. Character journey and Surreal narrative can use a simple visual cause and effect. Vary subjects and environments and respect medium locks. Do not force frantic movement onto quiet music.'''


SLATE_SYSTEM+='''
Give each proposal a different main movement and visible payoff, in addition to a different setting or subject where these are unlocked. Quiet tracks can shape precise gestures, tactile interactions or changing group spacing. Do not default to a lone figure drifting in a dim room and ending in stillness. If artist_direction names a subject or setting, interpret it visibly. A style-only reference guides the look while the action remains open to invention.'''


def slate_schema(approach,medium,count=6):
    return dict(type='object',additionalProperties=False,required=['music_direction','approaches','media','premises'],properties=dict(
        music_direction=dict(type='string',minLength=1,maxLength=700),
        approaches=dict(type='array',minItems=count,maxItems=count,items=dict(type='string',enum=[approach] if approach!='none' else list(APPROACHES))),
        media=dict(type='array',minItems=count,maxItems=count,items=dict(type='string',enum=[medium] if medium!='none' else MEDIA)),
        premises=dict(type='array',minItems=count,maxItems=count,items=dict(type='string',minLength=1,maxLength=240))))


def validate_slate(value,approach,medium,count=6):
    if not isinstance(value,dict) or set(value)!={'music_direction','approaches','media','premises'}:raise ValueError(f'Return music_direction and {count} each of approaches, media and premises')
    if not isinstance(value['music_direction'],str) or not value['music_direction'].strip():raise ValueError('Describe the music-informed visual direction')
    for key,allowed in [('approaches',[approach] if approach!='none' else APPROACHES),('media',[medium] if medium!='none' else MEDIA)]:
        items=value[key]
        if not isinstance(items,list) or len(items)!=count or any(x not in allowed for x in items):raise ValueError(f'Use {count} allowed {key} values and respect explicit locks')
    if approach=='none' and len(set(value['approaches']))!=count:raise ValueError(f'Choose {count} different directing approaches')
    if not isinstance(value['premises'],list) or len(value['premises'])!=count or any(not isinstance(p,str) or len(p.split())<5 for p in value['premises']):raise ValueError('Give each candidate a specific subject, setting, action and consequence')
    if len({p.casefold().strip() for p in value['premises']})!=count:raise ValueError(f'Write {count} different premises within the requested locks')
    return value


def enriched_review_schema(base):
    schema=copy.deepcopy(base); item=schema['properties']['reviews']['items']
    extra=dict(direction_fit={'type':'string','enum':['strong','weak']},development_fit={'type':'string','enum':['strong','weak']},
        direction_reason={'type':'string','minLength':1,'maxLength':280})
    item['properties'].update(extra); item['required']+=list(extra)
    return schema


REVIEW_EXTRA='''
Evaluate the ACTUAL subject, action, motion_cycle, camera and treatment, not merely a persuasive rationale. direction_fit is strong only when they follow the assigned directing approach, the music_direction's energy/groove/emotional character, artist intent and explicit medium lock. Musical fit always precedes novelty.
Check the concrete requirements in the assigned description and premise. A montage must show at least two distinct images connected through actual cuts; a choreographed world needs interacting environmental elements; a character journey needs a goal and action changing its situation. Do not mark a generic single-figure glide strong merely because its label names one of these approaches. In direction_reason cite the actual actions or shot transitions that demonstrate the approach. Reusing one setting/material across peers without an artist lock should not make all premises automatically fresh.
development_fit is strong when the movement can evolve over a longer film and the proposed actions and cuts fit this excerpt. Changes of footwork, weight, shape or formation can carry the entire clip. A camera zoom over a frozen object, vague promises of rhythm, or a repeated reset is weak. When measured rhythm is supplied, look for a few readable physical accents and movement between them. Quiet observation and restrained motion are valid when they express the music. For sub-three-second tests one continuous action is appropriate. Explain any repair in terms of a visible action, not added plot.'''


REVIEW_EXTRA+='''
Compare what each subject actually does and where that action leads. A different prop, title or medium is insufficient if the main movement and payoff recur. Look for a visible interpretation of a specific artist reference in the staging or action. A held ending is valid when it follows from this concept's action.'''


def validate_enriched_review(value,cues,base_validator,base_fields):
    if not isinstance(value,dict) or set(value)!={'reviews'} or not isinstance(value['reviews'],list):raise ValueError('Return three complete candidate reviews')
    extra={'direction_fit','development_fit','direction_reason'}
    for r in value['reviews']:
        if not isinstance(r,dict) or set(r)!=set(base_fields)|extra:raise ValueError('Include direction_fit, development_fit and direction_reason in each review')
        if r['direction_fit'] not in ('strong','weak') or r['development_fit'] not in ('strong','weak') or not isinstance(r['direction_reason'],str) or not r['direction_reason'].strip():raise ValueError('Assess actual direction and development potential')
    base={'reviews':[{k:r[k] for k in base_fields} for r in value['reviews']]}
    base_validator(base,cues)
    for r,canonical in zip(value['reviews'],base['reviews']):
        r['revision_needed']=canonical['revision_needed'] or r['direction_fit']=='weak' or r['development_fit']=='weak'
        if r['revision_needed'] and not r['feedback'].strip():r['feedback']='Revise actual choreography, pacing and story progression to fit the assigned direction and music, preserving explicit locks.'
    return value


def eligible(review):
    return review['music_fit']=='grounded' and review['direction_fit']=='strong' and review['development_fit']=='strong' and review['novelty']!='repeated' and not review['revision_needed']


def automatic_choice(reviews,directions,counts,seed,regenerate,key):
    accepted=[r for r in reviews if eligible(r)]
    if not accepted:raise ValueError('No candidate passed musical fit, directing fit and development review; increment regenerate or refine artist direction. No rendering started.')
    weights=[(2. if r['novelty']=='fresh' else 1.)/(1+counts.get(directions[r['index']-1]['name'],0)) for r in accepted]
    rng=random.Random(f'director-auto-v1:{key}:{seed}:{regenerate}')
    chosen=rng.choices(accepted,weights=weights,k=1)[0]['index']
    return chosen,[dict(index=r['index'],weight=round(w,6)) for r,w in zip(accepted,weights)]


def build_pool(ask,user,context,recent,cues,approach,medium,counts,validate,concept_schema,base_review_schema,base_review_system,base_validator,single_system,revision_system,max_tokens,count=6):
    menu=list(APPROACHES); random.Random(user['generation_seed']).shuffle(menu)
    slate=ask('directing_slate',SLATE_SYSTEM,{**user,'task':f'Choose {count} music-compatible directing approaches and a visual music brief. Respect the category locks.',
        'approach_menu':{name:APPROACHES[name] for name in menu},'recent_approach_counts':counts},slate_schema(approach,medium,count),lambda v:validate_slate(v,approach,medium,count),min(max_tokens,1536))
    directions=[dict(name=name,description=APPROACHES[name],premise=slate['premises'][i]) for i,name in enumerate(slate['approaches'])]
    exploration={k:v for k,v in context.items() if k not in ('recent_visual_choices','recent_subject_counts')}
    value={'concepts':[]}; revisions=[]; failures=[]; reviews=[]
    single_schema=dict(type='object',additionalProperties=False,required=['concept'],properties=dict(concept=concept_schema))

    def candidate_schema(index):
        # Put mandatory H3 syntax in the constrained decoder as well as prose.
        # Some local models otherwise keep paraphrasing the repair instruction.
        if directions[index]['name']!='Associative montage' or user['duration_seconds']<3:return single_schema
        import copy
        schema=copy.deepcopy(single_schema)
        motion=schema['properties']['concept']['properties']['motion_cycle']
        motion['description']='Use [Shot 1] and a timed [Shot 2]. Describe two distinct moving images and name the visible shape, motion or colour that connects them across the cut.'
        return schema

    def writer_payload(index):
        return {**user,'music_direction':slate['music_direction'],'directing_approach':directions[index],
            'animation_medium_lock':medium,'suggested_compatible_medium':slate['media'][index],
            'diversity_context':exploration,'reserved_titles':[c['title'] for i,c in enumerate(value['concepts']) if i!=index]}

    def parse_candidate(v,index):
        if not isinstance(v,dict) or set(v)!={'concept'} or not isinstance(v['concept'],dict):raise ValueError('Return one complete concept object')
        if medium!='none' and not str(v['concept'].get('treatment','')).strip().casefold().startswith(medium.casefold()+':'):
            raise ValueError('Begin treatment with the exact locked medium label followed by a colon: '+medium+': . Keep its animation grammar throughout.')
        if directions[index]['name']=='Associative montage' and user['duration_seconds']>=3:
            import re
            motion=str(v['concept'].get('motion_cycle',''))
            motion=re.sub(r'\bmatch[- ]cut(?:ting|s)?\b','match cut',motion,flags=re.IGNORECASE)
            motion=re.sub(r'(?<!\[)\bShot (\d+)\b(?!\])',r'[Shot \1]',motion,flags=re.IGNORECASE)
            v['concept']['motion_cycle']=motion
            # Preserve the model's actual edit and images; only supply H3's
            # missing delimiters around an explicitly described match cut.
            if '[Shot 1]' not in motion and '[Shot 2]' not in motion:
                transition=re.search(r'\bmatch[ -]cuts?\b',motion,re.IGNORECASE)
                if transition and motion[:transition.start()].strip() and motion[transition.end():].strip():
                    motion='[Shot 1] '+motion[:transition.start()]+'match cut [Shot 2] '+motion[transition.end():]
                    v['concept']['motion_cycle']=motion
            if '[Shot 1]' not in motion or '[Shot 2]' not in motion:
                raise ValueError('Associative montage needs [Shot 1] and a timed [Shot 2] with a visible connection between distinct images.')
            # The editor judges the visual connection. A literal keyword is
            # neither necessary nor sufficient to establish a match cut.
        merged=list(value['concepts'])
        validate({'concepts':[v['concept']]},1)
        used_titles={c['title'].strip().casefold() for i,c in enumerate(merged) if i!=index}
        title=v['concept']['title'].strip()
        if title.casefold() in used_titles:
            # Titles are labels. Keep the proposal and let the content checks
            # decide whether it is actually distinct from the other concepts.
            limit=concept_schema['properties']['title']['maxLength']
            number=2
            while True:
                suffix=f' ({number})'
                alternative=title[:limit-len(suffix)].rstrip()+suffix
                if alternative.casefold() not in used_titles:
                    v['concept']['title']=alternative
                    break
                number+=1
        if index==len(merged):merged.append(v['concept'])
        else:merged[index]=v['concept']
        validate({'concepts':merged},len(merged))
        return v

    for index in range(count):
        payload=writer_payload(index)
        payload['task']='Create ONE original complete concept using the assigned directing approach and musical visual brief. The medium is independent of the directing approach. Respect artist direction, exclusions and explicit medium lock; use actual descriptive field values. When animation_medium_lock is not none, begin treatment with that EXACT label followed by a colon. Explore a new premise and visible action; do not reuse reserved titles.'
        result=ask('concept_'+str(index+1),single_system,payload,candidate_schema(index),lambda v:parse_candidate(v,index),max_tokens)
        value['concepts'].append(result['concept'])
    review_schema=enriched_review_schema(base_review_schema)
    base_fields=base_review_schema['properties']['reviews']['items']['required']
    for round_index in range(3):
        combined=[]
        for start in range(0,count,3):
            local=value['concepts'][start:start+3]
            payload=dict(task='Review these three proposals against the music, their assigned directing approaches, explicit locks and development requirements.',
                music_cues=cues,music_direction=slate['music_direction'],measured_rhythm=user.get('measured_rhythm',{}),
                artist_direction=user['artist_direction'],exclusions=user['exclusions'],
                profile=user['profile'],duration_seconds=user['duration_seconds'],concepts=local,
                assigned_directions=[dict(index=i+1,**directions[start+i]) for i in range(3)],animation_medium_lock=medium,
                peer_signatures=[dict(title=c['title'],subject=c['subject'][:160],premise=directions[i]['premise'],
                    ending=c['seam_plan'][:160]) for i,c in enumerate(value['concepts']) if not start<=i<start+3],
                diversity_context=context)
            result=ask('concept_review_'+str(start+1),base_review_system+REVIEW_EXTRA,payload,review_schema,
                lambda v:validate_enriched_review(v,cues,base_validator,base_fields),min(max_tokens,1800))
            combined.extend([{**r,'index':r['index']+start} for r in result['reviews']])
        reviews.append(dict(reviews=combined))
        issues=[r for r in combined if r['revision_needed']]
        if not issues or round_index==2:break
        for issue in issues:
            index=issue['index']-1; payload=writer_payload(index)
            payload.update(task='Revise ONLY this candidate to fix the review. Preserve the assigned directing approach and category locks. When animation_medium_lock is not none, begin treatment with that EXACT label followed by a colon. Musical fit and developing visible actions have priority. Return one complete concept.',
                concept_to_replace=value['concepts'][index],review_feedback=issue,concept_index_to_replace=index+1)
            try:result=ask('concept_revision_'+str(index+1),revision_system,payload,candidate_schema(index),lambda v:parse_candidate(v,index),max_tokens)
            except ValueError as error:failures.append(dict(index=index+1,error=str(error))); continue
            value['concepts'][index]=result['concept']; revisions.append(index+1)
    return dict(value=value,memory_snapshot=context,music_cues=cues,editor_reviews=reviews,revised_concept_indices=revisions,
        revision_failures=failures,directions=directions,music_direction=slate['music_direction'],approach_counts_snapshot=counts,
        category_locks=dict(directing_approach=approach,animation_medium=medium))
