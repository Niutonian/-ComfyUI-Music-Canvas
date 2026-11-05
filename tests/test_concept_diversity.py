import copy
import json
from pathlib import Path
import tempfile
import unittest
from concept_diversity import ConceptMemory,diversity_context,music_cues,validate_review,candidate_flags,medium_family


def concept(subject='A paper boat',medium='Paper cut stop-motion'):
    return dict(title='Test choice',subject=subject,environment='A painted inlet',treatment=medium,motion_cycle='Launches then completes a circle')


class DiversityTests(unittest.TestCase):
    def test_medium_uses_primary_technique_and_ignores_negated_comparisons(self):
        self.assertEqual(medium_family('Cinematic photographic or live-action; no graphic or clay styling'),'photographic')
        self.assertEqual(medium_family('Stylized 3D with realistic cut-paper props'),'three_dimensional')
        self.assertEqual(medium_family('Painted animation with brushwork and no paper texture'),'painted')
        self.assertEqual(medium_family('Hand-drawn 2D with paper-cut scenery'),'drawn')

    def test_archive_bootstrap_deduplicates_rerenders_and_remembers_selected_choices(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('first','copy'):
                folder=root/'output/music_canvas'/name; folder.mkdir(parents=True)
                (folder/'animation_brief.json').write_text(json.dumps({'concept':concept()}))
            memory=ConceptMemory(root/'user',root/'output')
            self.assertEqual(len(memory.recent()),1)
            memory.remember('request:1',concept())
            memory.remember('request:1',concept('Different subject')) # Same cached selection, no extra event.
            self.assertEqual(len(memory.recent()),1)
            memory.remember('request:2',concept('A mechanical creature','Clay puppet stop-motion'))
            self.assertEqual(len(memory.recent()),2)
            self.assertEqual(memory.recent()[0]['medium'],'clay_puppet')
            # Reopening the DB does not reimport archive copies or create more choices.
            self.assertEqual(len(ConceptMemory(root/'user',root/'output').recent()),2)

    def test_medium_order_varies_by_seed_and_favors_underused_media_without_bans(self):
        rows=[dict(title='Old',subject='Boat',environment='Sea',motion_cycle='Sailing',medium='paper',subject_family='watercraft')]
        first=diversity_context(rows,10); second=diversity_context(rows,11)
        self.assertEqual(first,diversity_context(rows,10))
        self.assertNotEqual(first['medium_options_less_recent_first'],second['medium_options_less_recent_first'])
        self.assertIn('Paper',first['medium_options_less_recent_first'][-1])
        self.assertIn('priority',first['instruction'])
        self.assertEqual(candidate_flags([concept()],rows)[0]['recent_combination_uses'],1)

    def test_cues_are_supplied_evidence_and_review_cannot_invent_ids(self):
        evidence=dict(summary='A sparse intimate song',instruments=['piano'],moods=['tender'],lyrics='UNAPPROVED')
        before=copy.deepcopy(evidence); cues=music_cues(evidence)
        self.assertEqual(evidence,before)
        self.assertNotIn('UNAPPROVED',json.dumps(cues))
        value={'reviews':[dict(index=i,music_fit='grounded',cue_ids=['cue_01','cue_02'],fit_reason='Relates to piano and tenderness',
            novelty='fresh',revision_needed=False,feedback='') for i in (1,2,3)]}
        validate_review(value,cues)
        value['reviews'][0]['revision_needed']=True
        validate_review(value,cues)
        self.assertFalse(value['reviews'][0]['revision_needed'])
        value['reviews'][0]['cue_ids']=['cue_99']
        with self.assertRaisesRegex(ValueError,'supplied musical cue IDs'):validate_review(value,cues)
        value['reviews'][0]['cue_ids']=['cue_01']
        with self.assertRaisesRegex(ValueError,'distinct supplied musical cues'):validate_review(value,cues)

    def test_sparse_evidence_does_not_require_inventing_a_second_cue(self):
        cues=music_cues({'summary':'A calm instrumental'})
        value={'reviews':[dict(index=i,music_fit='grounded',cue_ids=['cue_01'],fit_reason='Calm pacing from the summary',
            novelty='familiar',revision_needed=False,feedback='') for i in (1,2,3)]}
        validate_review(value,cues)


if __name__=='__main__':unittest.main()
