import hashlib
import unittest
from tools.audit_publication import audit

class PublicationMedia(unittest.TestCase):
    def test_only_the_named_and_fingerprinted_showcase_is_accepted(self):
        name='docs/media/comparison-a.gif';data=b'GIF89a'+b'preview'
        media={name:dict(mime_type='image/gif',size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest())}
        self.assertEqual(audit([name],lambda p:data,{name},{name},media),[])
        changed=b'GIF89a'+b'changed'
        self.assertEqual(audit([name],lambda p:changed,{name},{name},media)[0]['rule'],'showcase-media-not-verified')

    def test_other_binary_files_do_not_gain_a_media_exception(self):
        name='docs/media/full-song.mp4'
        findings=audit([name],lambda p:b'\xff\x00binary',{name},{name},{name:{}})
        self.assertEqual(findings[0]['rule'],'unexpected-binary')

    def test_expected_hash_cannot_approve_the_wrong_file_type(self):
        name='docs/media/comparison-a.gif';data=b'not an animation'
        media={name:dict(mime_type='image/gif',size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest())}
        self.assertEqual(audit([name],lambda p:data,{name},{name},media)[0]['rule'],'showcase-media-not-verified')

if __name__=='__main__':unittest.main()
