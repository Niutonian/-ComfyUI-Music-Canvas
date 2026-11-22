"""Direct a whole music film as distinct, temporally connected H3 scenes."""
import copy
import json
import math
import time
from pathlib import Path
from .audio_performance import StageCache,identity
from .director_evidence import MOVEMENT_DIRECTION, bound_evidence, measured_rhythm
from . import ollama_director as ollama
from .sequential import plan_segments

VERSION='music-canvas-timeline-7-rhythmic-phrases'
VISUAL_CONTINUITY_RULES='''
VISUAL CONTINUITY
Build one production bible for THIS film from its chosen concept and musical character; never reuse a stock subject across songs. identity_anchors names the enduring silhouette, proportions, surface, colour arrangement and distinctive features of recurring subjects, using short consistent names. It describes appearance, not an opening pose, location, action or completed ending. Do not put properties that the story will intentionally transform into immutable anchors.
lighting_continuity defines the baseline light sources, light quality and shadow logic within a location. Keep light sources attached to the world when the camera changes angle, rather than relighting every cut. Explicitly motivated changes of light, time or location are allowed.
spatial_continuity defines screen direction, relative positions and prop/contact logic within a shared space. Preserve them across cuts unless a visible turn, establishing shot or planned transition explains a change. For associative montage use a visible match in shape, motion or colour instead of imposing one continuous geography.
motion_grammar defines this medium's animation cadence, weight, deformation and secondary motion. A consistent animation language must still produce different actions, scales and camera views, never repeated choreography or a frozen scene.
Separate permanent design from changing scene state. The current state and recorded transformations override the opening appearance for attributes the story explicitly changes; carry those changes forward. Never restore an earlier pose, costume, object condition or location merely to repeat the initial design. Do not add new wardrobe, markings or props just to make a cut different.
For every shot use the same short subject names. Write visible action, composition and camera movement. For later shots include a concrete handoff when relevant: continuing a gesture, retaining a held prop, preserving travel direction, or matching a shape across an intentional montage. The preceding shot is completed HISTORY, not an action to reenact. A new shot develops its result. Full appearance anchors are inserted by the compiler; do not spend the shot description rephrasing them. Do not invent image-reference labels or reference assets.'''
SYSTEM='''You direct a complete music film over the supplied TOTAL duration. Return only JSON matching the schema.
The base concept supplies artistic identity, not a short clip to repeat. Expand it into setup, development, escalation and resolution across the whole timeline. Ignore per-clip loop/reset instructions in the source prompt. Never restart the same animation at every segment. Each scene introduces a new action, discovery, state or relationship while retaining a coherent medium, palette and subject design.
Musical observations are estimates, not verified artist biography. Use only supplied sonic evidence and approved lyrics; never invent words, beat measurements or artist likenesses. Describe visible animation with anticipation, action and follow-through. Use a consistent medium-specific motion grammar.
For scene batches, return exactly the requested indices in order. First start_state must exactly equal the supplied previous_end_state when present. Within the batch each start_state must exactly copy the preceding end_state. Each scene must advance the visible state; do not freeze or reset to the original opening. The final scene resolves the GLOBAL arc rather than starting another repetition.
shots use LOCAL scene time, beginning at 0, strictly increasing, inside that scene's duration. Use one shot for scenes under 3 seconds, and two or three purposeful shots for longer scenes when appropriate. Every shot includes subject action, framing and camera behavior. If supplied beats suggest useful cut points, prefer them; exact generated synchronization is not guaranteed. No replacement soundtrack, captions, logos or lip-sync. No flashing. Do not put negative ban-lists into the visual description.'''
SYSTEM+='''
Be concise: each text field is one short sentence, at most 24 words; shot descriptions may use 45 words. Copy continuity states verbatim rather than elaborating them. The global arc describes visible developments only. Do not invent musical entrances, drops, fades or changes; local musical evidence is the only basis for such claims, and music discussion belongs in musical_rationale. Keep the established artistic medium consistent.'''
SYSTEM+='''
Each slot has an assigned dramatic phase. Develop THAT phase at its global position. The climax introduces a major new visual event, leaving the final resolution for the resolution phase. Do not repeat the resolution action in the climax. end_state MUST describe the final visible state of the LAST shot, never a stale copy of the preceding scene's state. Shot descriptions contain only visible action, framing and camera movement, with no duration labels, timestamp ranges, field labels or soundtrack descriptions. Put cut times only in shots.at. Finish each sentence naturally.'''
SYSTEM+=VISUAL_CONTINUITY_RULES
SYSTEM+='\n'+MOVEMENT_DIRECTION
STORY_REALIZATION='''
An edited story plan is supplied. Its assigned_event_contract replaces the broad phase brief. Realize exactly that new event and earn its stated consequence through visible actions in the shots. Preserve the supplied opening and all persistent facts. Completed events are history: do not undo a completed release, resurrect a dissolved subject, arrive early, or replay a previous action with new adjectives. The final payoff occurs only in the final story scene. Camera movement alone is not the assigned development. Keep the selected artistic medium and palette. State fields are carried by the pipeline; focus on coherent, specific animated action that actually reaches the required ending.'''
STORY_REALIZATION+='''
Realize the contract through the rhythm of the action. For dance, keep enough of the body in frame to read weight and footwork. Add intermediate steps, rebounds and changes in level or direction that lead to the assigned result without changing it. Let the current motion carry into the next shot. Each shot description should specify what physically moves and how its speed, direction or shape changes. Use prose that H3 can depict directly. Avoid scenes spent only explaining a premise. Keep shot timestamps in shots.at; describe accents as part of the action, not as additional cut markers.'''

def string(limit=240): return {'type':'string','minLength':1,'maxLength':limit}
def object_schema(fields):
    return dict(type='object',additionalProperties=False,required=list(fields),properties=fields)
BIBLE_SCHEMA=object_schema({k:string(960 if k=='visual_style' else 600) for k in ('title','visual_style','identity_anchors','palette','world','setup','development','climax','resolution')})
for _field in ('lighting_continuity','spatial_continuity','motion_grammar'):
    BIBLE_SCHEMA['properties'][_field]=string(360)
    BIBLE_SCHEMA['required'].append(_field)
SHOT_SCHEMA=object_schema(dict(at={'type':'number'},description=string(720)))
SCENE_SCHEMA=object_schema(dict(index={'type':'integer'},narrative_beat=string(720),start_state=string(600),end_state=string(600),transition=string(720),
    musical_rationale=string(),shots=dict(type='array',minItems=1,maxItems=3,items=SHOT_SCHEMA)))


class PlanningLimit(ValueError): pass
class PlanningRepairError(ValueError): pass

def timeline_plan(total_seconds,segment_seconds):
    if not math.isfinite(total_seconds) or total_seconds<1/24: raise ValueError('Total duration must contain at least one video frame')
    return plan_segments(total_seconds,1,segment_seconds)


def prepare_scenes(value,slots,previous=None,analysis=None):
    """Carry known states and schedule model-suggested cuts on the actual frame grid.

    Content validation stays strict. Timing and exact continuity strings belong to
    the pipeline, rather than depending on the language model copying numbers/text.
    """
    value=copy.deepcopy(value)
    if not isinstance(value,dict) or not isinstance(value.get('scenes'),list) or len(value['scenes'])!=len(slots):
        return value
    adjustments=value.setdefault('_planning_adjustments',[])
    if not isinstance(adjustments,list): raise ValueError('Invalid planning adjustment metadata')
    analysis=analysis or {}
    indices=[s.get('index') if isinstance(s,dict) else None for s in value['scenes']]
    wanted=[slot['index'] for slot in slots]
    if all(isinstance(i,int) and not isinstance(i,bool) for i in indices) and sorted(indices)==sorted(wanted) and indices!=wanted:
        by_index={s['index']:s for s in value['scenes']}
        value['scenes']=[by_index[index] for index in wanted]
        adjustments.append(dict(kind='ordered_scene_slots',original_indices=indices,scheduled_indices=wanted))
    for scene,slot in zip(value['scenes'],slots):
        if not isinstance(scene,dict): continue
        if scene.get('index')!=slot['index'] or isinstance(scene.get('index'),bool):
            adjustments.append(dict(scene=slot['index'],kind='assigned_scene_slot',original_index=scene.get('index')))
            scene['index']=slot['index']
        if previous is not None and scene.get('start_state')!=previous:
            scene['start_state']=previous
            adjustments.append(dict(scene=slot['index'],kind='carried_previous_end_state'))
        previous=scene.get('end_state')
        shots=scene.get('shots')
        if not isinstance(shots,list) or not 1<=len(shots)<=3: continue
        if any(not isinstance(s,dict) or set(s)!={'at','description'} or not isinstance(s['description'],str) or not s['description'].strip() for s in shots):
            continue
        times=[s['at'] for s in shots]
        if any(isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) for t in times):
            raise ValueError('Shot times must be finite numbers')
        if slot['duration']<3 and len(shots)>1:
            scene['shots']=[dict(at=0.,description='One continuous shot. '+' Then '.join(s['description'] for s in shots))]
            adjustments.append(dict(scene=slot['index'],kind='short_scene_continuous_shot',original_times=times,scheduled_times=[0.]))
            continue
        start=slot['start_seconds']; duration=slot['duration']; frames=slot['frames']
        if start>0 and abs(times[0]-start)<1/48 and all(start<=t<=start+duration for t in times):
            times=[t-start for t in times]
            adjustments.append(dict(scene=slot['index'],kind='absolute_to_local_cut_times'))
        count=len(shots)
        # Leave a readable final shot instead of allowing a cut on the end boundary.
        gap=min(24,max(1,frames//count))
        scheduled=[0]
        for index in range(1,count):
            lower=scheduled[-1]+gap
            upper=frames-(count-index)*gap
            suggested=times[index]
            requested=round(suggested*24) if 0<suggested<duration else round(frames*index/count)
            target=max(lower,min(upper,requested))
            # Snap nearby cuts to downbeats first, then ordinary beats. Never drag
            # a cut across the scene to reach an unrelated beat.
            for key in ('downbeats','beats'):
                candidates=[]
                for beat in analysis.get(key) or []:
                    if isinstance(beat,bool) or not isinstance(beat,(int,float)) or not math.isfinite(beat): continue
                    if not start<beat<start+duration: continue
                    frame=round((beat-start)*24)
                    if lower<=frame<=upper and abs(frame-target)<=6: candidates.append(frame)
                if candidates:
                    target=min(candidates,key=lambda frame:(abs(frame-target),frame))
                    break
            scheduled.append(target)
        scheduled_times=[frame/24 for frame in scheduled]
        original_times=[s['at'] for s in shots]
        if original_times!=scheduled_times:
            for shot,at in zip(shots,scheduled_times): shot['at']=at
            adjustments.append(dict(scene=slot['index'],kind='scheduled_local_cut_times',
                original_times=original_times,scheduled_times=scheduled_times))
    return value

def validate_scenes(value,slots,previous=None,prior_actions=()):
    if not isinstance(value,dict) or not isinstance(value.get('scenes'),list) or len(value['scenes'])!=len(slots):
        raise ValueError('Return exactly one scene for each supplied timeline slot')
    actions=set(prior_actions)
    for scene,slot in zip(value['scenes'],slots):
        if not isinstance(scene,dict): raise ValueError('Each scene must be a JSON object')
        expected=set(SCENE_SCHEMA['properties'])
        if set(scene)!=expected:
            raise ValueError(f'Scene {slot["index"]} fields: missing {sorted(expected-set(scene))}, unexpected {sorted(set(scene)-expected)}')
        if isinstance(scene['index'],bool) or scene['index']!=slot['index']:
            raise ValueError(f'Scene index {scene["index"]} does not match timeline slot {slot["index"]}')
        for field in ('narrative_beat','start_state','end_state','transition','musical_rationale'):
            if not isinstance(scene[field],str) or not scene[field].strip(): raise ValueError('Scene fields must contain concrete descriptions')
        if previous is not None and scene['start_state']!=previous:
            raise ValueError('Copy the previous scene end_state exactly into the next start_state')
        if slot['duration']>=3 and scene['start_state'].strip().casefold()==scene['end_state'].strip().casefold():
            raise ValueError('This scene returns no visible progression; advance its end state')
        shots=scene['shots']
        if not isinstance(shots,list) or not 1<=len(shots)<=3: raise ValueError('A scene needs one to three shots')
        times=[]
        for shot in shots:
            if not isinstance(shot,dict) or set(shot)!={'at','description'} or not isinstance(shot['description'],str) or not shot['description'].strip(): raise ValueError('Invalid shot description')
            at=shot['at']
            if isinstance(at,bool) or not isinstance(at,(int,float)) or not math.isfinite(at) or not 0<=at<slot['duration']: raise ValueError('Shot cut falls outside its scene')
            times.append(at)
        if times[0]!=0 or any(a>=b for a,b in zip(times,times[1:])): raise ValueError('Shots must start at zero and advance in local scene time')
        if slot['duration']<3 and len(shots)!=1: raise ValueError('Short test scenes use one readable shot')
        action=' '.join(' '.join(s['description'].casefold().split()) for s in shots)
        if action in actions: raise ValueError('Repeated scene action: create a new development rather than replaying a prior animation')
        actions.add(action); previous=scene['end_state']
    return value['scenes']

def visual_continuity(bible):
    """A stable per-film design, distinct from evolving scene/pose state."""
    return {key:bible[key] for key in ('visual_style','identity_anchors','palette','world',
        'lighting_continuity','spatial_continuity','motion_grammar') if isinstance(bible.get(key),str) and bible[key].strip()}


def shot_history(scene):
    """Keep shot history out of compiled prompts so old actions are not replayed."""
    if not scene:return None
    return dict(scene_index=scene['index'],description=scene['shots'][-1]['description'],end_state=scene['end_state'])


def story_arc(bible):
    # Send the identity once in visual_continuity, not a second copy of it in
    # global_treatment. This leaves room for shot history in smaller contexts.
    return {key:value for key,value in bible.items() if key not in visual_continuity(bible)}


def compile_scene(bible,scene):
    style=' '.join(bible[k].strip().rstrip('.')+'.' for k in ('visual_style','palette'))
    anchors='Preserve these recurring designs only when visible: '+bible['identity_anchors'].strip().rstrip('.')+'.'
    rules=' '.join(bible[key].strip().rstrip('.')+'.' for key in ('lighting_continuity','spatial_continuity','motion_grammar') if bible.get(key))
    state_rule='Carry forward the current visible state and established transformations, including motivated changes of light or location; these take precedence over the baseline for changed attributes.'
    parts=[]
    for index,shot in enumerate(scene['shots'],1):
        if index==1:
            parts.append('[Shot 1] '+style+' World design: '+bible['world'].strip().rstrip('.')+'. '+
                anchors+' '+rules+' '+state_rule+' Opening state: '+scene['start_state'].strip().rstrip('.')+'. '+shot['description'])
        else:
            parts.append(f"[Shot {index}] At 00:{shot['at']:06.3f}, the camera cuts to "+shot['description']+
                ' '+anchors+' Continue the established medium, palette and animation cadence, with consistent light sources within this location. '+
                'For a continuing action, preserve screen direction and prop contact across the cut. '+state_rule)
    return ('integrated_multimodal_description: '+' '.join(parts)+
            ' End state: '+scene['end_state']+'. '+scene['transition']+
            '\n\noverall_soundscape: N/A\n\nnon_diegetic_music: N/A')


def prepare_story_scenes(value,slots,previous,analysis,story):
    result=prepare_scenes(value,slots,previous,analysis)
    if not isinstance(result,dict) or not isinstance(result.get('scenes'),list): return result
    for scene,slot in zip(result['scenes'],slots):
        if not isinstance(scene,dict): continue
        contract=story['scenes'][slot['index']]
        for field,source in [('start_state','opening_state'),('end_state','consequence'),('narrative_beat','event')]:
            if scene.get(field)!=contract[source]:
                result.setdefault('_planning_adjustments',[]).append(dict(scene=slot['index'],kind='assigned_story_'+field))
                scene[field]=contract[source]
        # next_obligation is the NEXT scene's event. Including it in this
        # segment's generation prompt spends that event early and repeats it.
        transition='Let the action resolve into the stated end state with natural follow-through.'
        if scene.get('transition')!=transition:
            result.setdefault('_planning_adjustments',[]).append(dict(scene=slot['index'],kind='assigned_story_transition'))
            scene['transition']=transition
    return result


def shot_contract(scene, inspired_action=None):
    contract={key:scene[key] for key in ('index','opening_state','event','consequence','state_updates','is_resolution')}
    if scene['index']==0 and inspired_action:
        contract['opening_inspiration']=inspired_action
    return contract


def edit_scene_batch(request,bible,slots,value,story,previous,actions,analysis,preceding_shot=None):
    from .story_planner import EDITOR_SYSTEM,REVIEW_SCHEMA,validate_review,compact_context
    shot_editor_system=EDITOR_SYSTEM+'''
This is SHOT REALIZATION review. The story has already been edited. Each review_scenes entry contains its OWN assigned_event_contract and shots. Indices are zero-based. Compare an entry's shots ONLY with that entry's contract. Never require the event of a different index to happen here. Only shots can be rewritten at this stage. narrative_beat, start_state, end_state and transition are fixed pipeline bookkeeping; do not demand changes to them or a different story development. Each issue must identify a concrete problem in actual shots: a reset, missing required action/result, repeated completed action, or incompatible medium. A next-scene link describes what follows this scene; it is not another action required within this scene.'''
    shot_editor_system+='''
Check explicit appearance contradictions and impossible handoffs against the visual_continuity notes and preceding_shot when supplied. Preceding shots are history, never extra actions required here. Do not demand an unchanged pose, camera angle, costume visibility or lighting when a planned action, crop, transformation, new location or motivated light change explains the difference. Reject an explicit design change without a story cause, not omission of an anchor from a close-up; the compiler repeats the canonical appearance notes.'''
    shot_editor_system+='''
Assess whether the stated movement can be seen. A held beat or a quiet detail can be part of a phrase. Only flag passive staging when camera movement or atmospheric prose replaces the assigned physical action. Suggest a concrete gesture, impact or shift that fulfills the existing contract. Do not require precise synchronization or more cuts.'''
    reviews=[]; revisions=0; batch=value['scenes']
    limit=min(2,int(story.get('max_editor_revisions',2)))
    history=compact_context(story,story['scenes'],slots[0]['index'])
    history.pop('upcoming_outline',None)
    for revision in range(limit+1):
        user=dict(task='Review expanded H3 shot descriptions against the edited story contracts. Do the actions visibly earn the consequence?',
            global_treatment=story_arc(bible),visual_continuity=visual_continuity(bible),preceding_shot=preceding_shot,
            artist_direction=story.get('artist_direction',''),
            review_indices=[s['index'] for s in slots],
            review_scenes=[dict(index=s['index'],shots=s['shots'],assigned_event_contract=shot_contract(story['scenes'][s['index']],story.get('inspired_action'))) for s in batch],
            editable_fields=['shots'],pipeline_owned_fields=['narrative_beat','start_state','end_state','transition'],
            history=history)
        if story.get('story_inspiration'):user['story_inspiration']=story['story_inspiration']
        review=request(f'shot_editor_{slots[0]["index"]}_{revision}',user,REVIEW_SCHEMA,
            lambda v:validate_review(v,user['review_indices']),system_override=shot_editor_system)
        reviews.append(dict(stage='expanded_shots',revision=revision,indices=user['review_indices'],**review))
        if review['accepted']: break
        if revision==limit:
            confirmation=request(f'shot_editor_confirm_{slots[0]["index"]}',
                {**user,'remaining_objections':review['issues'],'task':'Adjudicate only the remaining objections against the visible shots and fixed contracts. Reject actual incompatible actions, resets, repeated completed events or missing endings. Accept compatible wording; do not impose stylistic preferences or invent a different story.'},
                REVIEW_SCHEMA,lambda v:validate_review(v,user['review_indices']),system_override=shot_editor_system)
            reviews.append(dict(stage='shot_adjudication',revision=revision,indices=user['review_indices'],**confirmation))
            if not confirmation['accepted']:raise PlanningRepairError('Shot editor could not resolve: '+'; '.join(i['feedback'] for i in confirmation['issues'])[:900])
            break
        for index in sorted(set(i['index'] for i in review['issues'])):
            position=next(i for i,s in enumerate(slots) if s['index']==index); slot=slots[position]
            contract=shot_contract(story['scenes'][index],story.get('inspired_action'))
            user=dict(task='Revise only the shots to fulfill this fixed story event and ending. Correct visible action rather than changing contract metadata. The next-scene link belongs to the following scene.',
                global_treatment=story_arc(bible),visual_continuity=visual_continuity(bible),
                artist_direction=story.get('artist_direction',''),
                preceding_shot=shot_history(batch[position-1]) if position else preceding_shot,
                slots=[dict(**slot,**measured_rhythm(analysis,slot['start_seconds'],slot['duration']))],assigned_event_contract=contract,
                previous_version=dict(index=index,shots=batch[position]['shots']),
                feedback=[i for i in review['issues'] if i['index']==index],history=compact_context(story,story['scenes'],index))
            if story.get('story_inspiration'):user['story_inspiration']=story['story_inspiration']
            schema=object_schema(dict(scenes=dict(type='array',minItems=1,maxItems=1,items=SCENE_SCHEMA)))
            revised=request(f'shot_revision_{index}_{revision}',user,schema,
                lambda v:validate_scenes(v,[slot],contract['opening_state']),
                prepare=lambda v:prepare_story_scenes(v,[slot],contract['opening_state'],analysis,story))
            batch[position]=revised['scenes'][0]
            value.setdefault('_planning_adjustments',[]).extend(revised.get('_planning_adjustments',[])); revisions+=1
        validate_scenes({'scenes':batch},slots,previous,actions)
    value['scenes']=batch
    return value,reviews,revisions

class MusicCanvasOllamaTimeline:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':dict(connection=('MUSIC_CANVAS_OLLAMA',),analysis_json=('STRING',{'multiline':True}),
            base_brief_json=('STRING',{'multiline':True}),base_prompt=('STRING',{'multiline':True}),
            total_seconds=('FLOAT',{'default':60.,'min':1/24,'max':2147483647.,'step':.25}),
            segment_seconds=('FLOAT',{'default':15.,'min':.25,'max':15.,'step':.25}),
            lyrics_approved=('BOOLEAN',{'default':False}),temperature=('FLOAT',{'default':.6,'min':0.,'max':1.5}),
            seed=('INT',{'default':42,'min':0,'max':2147483647,'control_after_generate':True}),
            max_tokens=('INT',{'default':3072,'min':512,'max':8192}),
            regenerate=('INT',{'default':0,'min':0,'max':2147483647})),
            'optional':dict(batch_size=('INT',{'default':4,'min':1,'max':4}),story_plan_json=('STRING',{'forceInput':True}))}
    RETURN_TYPES=('STRING','STRING','STRING')
    RETURN_NAMES=('scene_prompts_json','timeline_json','planning_report')
    FUNCTION='direct'
    CATEGORY='Music Canvas/Ollama'
    @classmethod
    def IS_CHANGED(cls,**kwargs): return float('nan')

    def direct(self,connection,analysis_json,base_brief_json,base_prompt,total_seconds,segment_seconds,lyrics_approved,
               temperature,seed,max_tokens,regenerate,batch_size=4,story_plan_json=''):
        import folder_paths
        import comfy.model_management as mm
        from comfy.utils import ProgressBar
        started=time.monotonic()
        plan=timeline_plan(total_seconds,segment_seconds)
        if not 1<=batch_size<=4: raise ValueError('Planner batch size must be 1–4')
        analysis=json.loads(analysis_json); brief=json.loads(base_brief_json)
        if not isinstance(analysis,dict) or not isinstance(brief,dict): raise ValueError('Connect analysis and the director brief')
        story=None
        if story_plan_json.strip():
            from .story_planner import validate_story_plan
            story=validate_story_plan(json.loads(story_plan_json),plan,analysis,brief)
        system=SYSTEM+STORY_REALIZATION if story else SYSTEM
        selected=next((m for m in ollama.models(connection['base_url']) if m['name']==connection['model']),None)
        if selected is None: raise ValueError('Selected local Ollama model is not installed')
        facts={k:analysis[k] for k in ('summary','moods','instruments','style_tags','production','sections','vocals','tempo_bpm','warnings','full_track_coverage','coverage_ratio') if k in analysis}
        if lyrics_approved: facts['lyrics']=analysis.get('lyrics')
        facts=bound_evidence(facts,5000)
        concept=brief.get('concept',{})
        art={k:concept[k] for k in ('title','subject','environment','palette','treatment','rationale') if k in concept}
        if brief.get('directing_approach'):
            art.update(directing_approach=brief['directing_approach'],music_direction=brief.get('music_direction',''))
            system+='\nPreserve the supplied directing approach in staging, choreography, camera and editing, and follow the visual music direction. Medium and directing approach are independent. A montage may advance through new visual relationships; performance through developing movement phrases; observation through gestures and discoveries. Do not convert every approach into the same character quest.'
        context=dict(total_seconds=total_seconds,segment_seconds=segment_seconds,scene_count=len(plan),
                     musical_evidence=facts,base_concept=art,source_prompt='' if art else base_prompt[:2000],exclusions=brief.get('exclusions',''),
                     directive='Expand this visual identity into a complete evolving film. Do not repeat the standalone clip or its loop/reset instructions.')
        artist_direction=brief.get('artist_direction')
        if isinstance(artist_direction,str) and artist_direction.strip():
            context['artist_direction']=artist_direction.strip()[:1200]
        if story and story.get('story_inspiration'):
            context['story_inspiration']=story['story_inspiration']
        common=dict(version=VERSION,model=connection['model'],digest=selected.get('digest'),context=context,
                    seed=seed,temperature=temperature,max_tokens=max_tokens,regenerate=regenerate,system=system,
                    rhythm=identity({k:analysis.get(k) for k in ('beats','downbeats','energy_envelope','chunks')}),
                    context_length=connection['context_length'],batch_size=batch_size,device=connection['device'])
        if story: common.update(edited_story_key=identity(story),shot_editor_policy=4)
        cache=StageCache(Path(folder_paths.get_user_directory())/'MusicCanvas'/'timeline_cache')
        approved_key=dict(common=common,stage='approved_timeline')
        approved=cache.get(approved_key)
        if isinstance(approved,dict) and isinstance(approved.get('timeline'),dict):
            cached_timeline=approved['timeline']
            try:
                validate_scenes({'scenes':[segment['scene'] for segment in cached_timeline['segments']]},plan)
                if cached_timeline.get('version')!=VERSION:raise ValueError('Old timeline version')
            except (ValueError,KeyError,TypeError):pass
            else:
                report={**approved['report'],'requests':0,'cache_hits':1,'approved_plan_cache_hit':True,
                    'release':ollama.release(connection['base_url'],connection['model']),'elapsed_seconds':time.monotonic()-started}
                return timeline_result(cached_timeline,report)
        recovery_key=dict(common=common,stage='terminal_recovery')
        recovery=cache.get(recovery_key) or {}
        recovery_round=recovery.get('round',0)
        if not isinstance(recovery_round,int) or not 0<=recovery_round<2147483647:recovery_round=0
        counts=dict(cache_hits=0,requests=0)
        progress=ProgressBar(len(plan)+1)
        ollama.OWNED_MODELS.add((connection['base_url'],connection['model']))

        def failure(stage,key,response,error,req=None,attempt=None):
            directory=cache.root/'failures'; directory.mkdir(exist_ok=True)
            content=json.dumps(dict(stage=stage,error=str(error),response=response,request=req,attempt=attempt,recovery_round=recovery_round),ensure_ascii=False,indent=2)
            (directory/(identity(key)+'.json')).write_text(content,encoding='utf-8')
            attempts=directory/'attempts'; attempts.mkdir(exist_ok=True)
            (attempts/(identity(key)+'_'+str(time.time_ns())+'.json')).write_text(content,encoding='utf-8')

        def request(stage,user,schema,validator,prepare=None,system_override=None):
            key=dict(common=common,stage=stage,user=user,schema=schema)
            if system_override: key['system_override']=system_override
            if stage.startswith('shot_revision'):key['repair_round']=recovery_round
            with cache.lock(key):
                cached=cache.get(key)
                if cached is not None:
                    try:
                        if prepare: cached=prepare(cached)
                        validator(cached)
                        if not (isinstance(cached,dict) and cached.get('accepted') is False):
                            counts['cache_hits']+=1; return cached
                    except (ValueError,TypeError,KeyError): pass
                if connection['device']=='GPU':
                    mm.unload_all_models(); mm.soft_empty_cache()
                req=dict(model=connection['model'],messages=[dict(role='system',content=system_override or system),dict(role='user',content=json.dumps(user,ensure_ascii=False))],
                         stream=False,format=schema,keep_alive='5m',
                         options=dict(temperature=min(temperature,.15) if system_override else temperature,
                            seed=(seed+int(identity(stage)[:6],16)+recovery_round*104729)%2147483647,
                            num_ctx=connection['context_length'],num_predict=min(max_tokens,max(512,connection['context_length']//2))))
                if connection['device']=='CPU': req['options']['num_gpu']=0
                if system_override: req['options']['num_predict']=min(req['options']['num_predict'],1536)
                if 'thinking' in selected.get('capabilities',connection.get('capabilities',[])): req['think']=False
                base_messages=copy.deepcopy(req['messages'])
                for attempt in range(3):
                    mm.throw_exception_if_processing_interrupted()
                    response=ollama.api(connection['base_url'],'/api/chat',req,timeout=600); counts['requests']+=1
                    if response.get('done_reason')=='length':
                        failure(stage,key,response,'token_limit',req,attempt)
                        raise PlanningLimit('Timeline planning reached its token limit; increase context/max_tokens for a single scene')
                    try:
                        value=json.loads(response['message']['content'])
                        if prepare: value=prepare(value)
                        validator(value)
                        if isinstance(value,dict) and value.get('accepted') is False:
                            failure(stage,key,response,'editor_rejected',req,attempt)
                            return value
                        cache.put(key,value); return value
                    except (ValueError,KeyError,TypeError) as error:
                        failure(stage,key,response,error,req,attempt)
                        if attempt==2: raise PlanningRepairError('Timeline repair failed: '+str(error)) from error
                        req['options']['seed']=(req['options']['seed']+104729)%2147483647
                        req['options']['temperature']=min(req['options']['temperature'],.35)
                        req['messages']=base_messages+[dict(role='user',content='The previous response failed validation: '+str(error)+'. Write a fresh complete replacement preserving the timing and event contracts. Finish all sentences naturally.')]

        def valid_bible(value):
            if not isinstance(value,dict) or set(value)!=set(BIBLE_SCHEMA['properties']) or any(not isinstance(v,str) or not v.strip() for v in value.values()):
                raise ValueError('The global film treatment needs every requested field')
        try:
            if story:
                bible=story['treatment']; valid_bible(bible)
            else: bible=request('global_treatment',dict(task='Design the global artistic identity and dramatic arc for the ENTIRE film.',**context),BIBLE_SCHEMA,valid_bible)
            progress.update_absolute(1)
            policy_key=dict(common=common,stage='batch_policy')
            policy=cache.get(policy_key)
            preferred=policy.get('batch_size') if isinstance(policy,dict) else None
            effective_batch=preferred if isinstance(preferred,int) and 1<=preferred<=batch_size else batch_size
            scenes=[]; previous=None; actions=[]; begin=0; adjustments=[]; shot_reviews=[]; shot_revisions=0
            while begin<len(plan):
                mm.throw_exception_if_processing_interrupted()
                slots=plan[begin:begin+effective_batch]
                local=[]
                for slot in slots:
                    a=slot['start_seconds']; b=a+slot['duration']
                    fraction=(a+slot['duration']/2)/total_seconds
                    phase='setup' if fraction<.25 else 'development' if fraction<.5 else 'climax' if fraction<.8 else 'resolution'
                    local_slot=dict(**slot,video_end=b,progress_fraction=a/total_seconds,
                        cut_time_reference='LOCAL seconds from zero, not video_start',last_valid_cut_seconds=(slot['frames']-1)/24,
                        dramatic_phase=phase,assigned_development=bible[phase],
                        **measured_rhythm(analysis,a,slot['duration']),
                        local_music=bound_evidence({'chunks':[c for c in (analysis.get('chunks') or []) if c.get('start',0)<b and c.get('end',0)>a]},1400))
                    if story:
                        from .story_planner import compact_context
                        local_slot.pop('assigned_development',None); local_slot.pop('dramatic_phase',None)
                        local_slot['assigned_event_contract']=shot_contract(story['scenes'][slot['index']],story.get('inspired_action'))
                        local_slot['world_history']=compact_context(story,story['scenes'],slot['index'])
                    local.append(local_slot)
                user=dict(task='Write the next unique animated scenes in the global story. Exact state continuity is required.',global_treatment=story_arc(bible),
                    visual_continuity=visual_continuity(bible),preceding_shot=shot_history(scenes[-1]) if scenes else None,
                    total_seconds=total_seconds,slots=local,previous_end_state=previous,
                    prior_story_beats=[s['narrative_beat'] for s in scenes[-8:]],musical_evidence=facts)
                if brief.get('directing_approach'):
                    user.update(directing_approach=brief['directing_approach'],music_direction=brief.get('music_direction',''))
                if 'artist_direction' in context:user['artist_direction']=context['artist_direction']
                if 'story_inspiration' in context:user['story_inspiration']=context['story_inspiration']
                schema=object_schema(dict(scenes=dict(type='array',minItems=len(slots),maxItems=len(slots),items=SCENE_SCHEMA)))
                try:
                    value=request('scenes_'+str(begin),user,schema,lambda v:validate_scenes(v,slots,previous,actions),
                        prepare=lambda v:prepare_story_scenes(v,slots,previous,analysis,story) if story else prepare_scenes(v,slots,previous,analysis))
                    if story:
                        value,checks,changes=edit_scene_batch(request,bible,slots,value,story,previous,actions,analysis,
                            preceding_shot=shot_history(scenes[-1]) if scenes else None)
                        shot_reviews.extend(checks); shot_revisions+=changes
                except (PlanningLimit,PlanningRepairError) as error:
                    if len(slots)==1: raise
                    effective_batch=max(1,len(slots)//2)
                    cache.put(policy_key,dict(batch_size=effective_batch))
                    print(f'[MusicCanvas Timeline] Reducing planning batches to {effective_batch} scenes: {error}',flush=True)
                    continue
                batch=validate_scenes(value,slots,previous,actions)
                adjustments.extend(value.get('_planning_adjustments',[]))
                scenes.extend(batch); previous=scenes[-1]['end_state']
                actions=[' '.join(' '.join(shot['description'].casefold().split()) for shot in s['shots']) for s in scenes]
                progress.update_absolute(1+len(scenes))
                begin+=len(batch)
        except (ValueError,KeyError,TypeError) as error:
            failure('terminal',recovery_key,None,error)
            with cache.lock(recovery_key):
                current=cache.get(recovery_key) or {}
                cache.put(recovery_key,dict(round=max(recovery_round,int(current.get('round',0)))+1))
            raise
        finally:
            released=ollama.release(connection['base_url'],connection['model'])
        prompts=[compile_scene(bible,scene) for scene in scenes]
        timeline=dict(version=VERSION,total_seconds=total_seconds,segment_seconds=segment_seconds,time_reference='selected video, seconds from zero',
            treatment=bible,segments=[dict(**slot,scene=scene,prompt=prompt) for slot,scene,prompt in zip(plan,scenes,prompts)],scene_prompts=prompts,
            model=connection['model'],model_digest=selected.get('digest'),seed=seed)
        timeline['planning_adjustments']=adjustments
        timeline['visual_continuity']=visual_continuity(bible)
        if story:
            timeline.update(story_plan=story,shot_editor_reviews=shot_reviews)
        report=dict(**counts,release=released,scene_count=len(scenes),elapsed_seconds=time.monotonic()-started,
                    distinct_prompts=len(set(prompts))==len(prompts),effective_batch_size=effective_batch,
                    planning_adjustments=adjustments,frame_accurate_cut_execution_guaranteed=False)
        report['visual_continuity']=dict(mode='prompt_only',appearance_repeated_per_shot=True,
            shot_history_used=True,visual_references_used=False,identity_guaranteed=False)
        if story: report.update(story_editor_enabled=True,shot_editor_reviews=shot_reviews,shot_editor_revisions=shot_revisions)
        cache.put(approved_key,dict(timeline=timeline,report=report))
        return timeline_result(timeline,report)


def timeline_result(timeline,report):
    return json.dumps(timeline['scene_prompts'],ensure_ascii=False),json.dumps(timeline,ensure_ascii=False,indent=2),json.dumps(report,indent=2)
