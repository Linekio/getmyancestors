from unittest.mock import patch

from getmyancestors.classes.tree import Fam, Indi, Tree


class TestTree:

    def test_add_indis(self, mock_session, sample_person_json):
        """Test adding a list of individuals to the tree."""

        def get_url_side_effect(url, headers=None):
            if "KW7V-Y32" in url:
                return sample_person_json
            return {"persons": [], "childAndParentsRelationships": [], "spouses": []}

        mock_session.get_url.side_effect = get_url_side_effect

        tree = Tree(mock_session)
        tree.add_indis(["KW7V-Y32"])

        assert "KW7V-Y32" in tree.indi
        person = tree.indi["KW7V-Y32"]
        assert person.fid == "KW7V-Y32"

    def test_add_parents(self, mock_session):
        """Test fetching parents creates family links."""
        tree = Tree(mock_session)
        child_id = "KW7V-CHILD"
        father_id = "KW7V-DAD"
        mother_id = "KW7V-MOM"

        # 1. Seed child with parent IDs
        child = Indi(child_id, tree)
        child.parents.add((father_id, mother_id))
        tree.indi[child_id] = child

        # 2. Mock parent relationship response (robustness)
        relationships_response = {
            "childAndParentsRelationships": [
                {
                    "parent1": {"resourceId": father_id},
                    "parent2": {"resourceId": mother_id},
                    "child": {"resourceId": child_id},
                }
            ]
        }
        mock_session.get_url.return_value = relationships_response

        # 3. Patch add_indis
        # We must simulate the actual effect of add_indis: creating the objects
        with patch.object(tree, "add_indis") as mock_add_indis:

            def add_indis_side_effect(fids):
                for fid in fids:
                    if fid not in tree.indi:
                        tree.indi[fid] = Indi(fid, tree)

            mock_add_indis.side_effect = add_indis_side_effect

            result = tree.add_parents({child_id})

            # 4. Assertions
            assert father_id in result
            assert mother_id in result

            # The key in tree.fam is 'FAM_<father_id>-<mother_id>'
            fam_key = f"FAM_{father_id}-{mother_id}"
            assert fam_key in tree.fam
            assert tree.indi[child_id] in tree.fam[fam_key].children

    def test_manual_family_linking(self, mock_session):
        """
        Verify that we can link individuals manually.
        """
        tree = Tree(mock_session)

        husb = Indi("HUSB01", tree)
        wife = Indi("WIFE01", tree)

        fam = Fam(husb, wife, tree)
        fam_key = fam.num  # This is the key used in Tree.ensure_family or manual add
        tree.fam[fam_key] = fam

        # Link manually as GEDCOM parser or other tools might
        husb.fams.add(fam)
        wife.fams.add(fam)

        assert fam.husband.id == "HUSB01"
        assert tree.fam[fam_key] == fam
