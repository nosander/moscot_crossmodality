from typing import Mapping, Optional, Tuple

import pytest

import numpy as np
import pandas as pd

from anndata import AnnData

from moscot.problems.cross_modality import TranslationProblem
from tests._utils import MockSolverOutput


class TestCrossModalityTranslationAnalysisMixin:
    @pytest.mark.parametrize(
        "src_attr", ["emb_src", {"attr": "obsm", "key": "emb_src"}, {"attr": "layers", "key": "counts"}]
    )
    @pytest.mark.parametrize(
        "tgt_attr", ["emb_tgt", {"attr": "obsm", "key": "emb_tgt"}, {"attr": "layers", "key": "counts"}]
    )
    @pytest.mark.parametrize("joint_attr", [None, "X_pca", {"attr": "obsm", "key": "X_pca"}])
    def test_translation_foo(
        self,
        adata_translation_split: Tuple[AnnData, AnnData],
        src_attr: Mapping[str, str],
        tgt_attr: Mapping[str, str],
        joint_attr: Optional[Mapping[str, str]],
    ):
        adata_src, adata_tgt = adata_translation_split
        expected_keys = {(i, "ref") for i in adata_src.obs["batch"].cat.categories}

        tp = (
            TranslationProblem(adata_src, adata_tgt)
            .prepare(batch_key="batch", src_attr=src_attr, tgt_attr=tgt_attr, joint_attr=joint_attr)
            .solve()
        )
        for src, tgt in expected_keys:
            trans_forward = tp.translate(source=src, target=tgt, forward=True)
            assert trans_forward.shape == tp[src, tgt].y.data_src.shape

            trans_backward = tp.translate(source=src, target=tgt, forward=False)
            assert trans_backward.shape == tp[src, tgt].x.data_src.shape

    @pytest.mark.parametrize("src_attr", ["emb_src", {"attr": "obsm", "key": "emb_src"}])
    @pytest.mark.parametrize("tgt_attr", ["emb_tgt", {"attr": "obsm", "key": "emb_tgt"}])
    @pytest.mark.parametrize("alternative_attr", ["X_pca", {"attr": "obsm", "key": "X_pca"}])
    def test_translate_alternative(
        self,
        adata_translation_split: Tuple[AnnData, AnnData],
        src_attr: Mapping[str, str],
        tgt_attr: Mapping[str, str],
        alternative_attr: Optional[Mapping[str, str]],
    ):
        adata_src, adata_tgt = adata_translation_split
        expected_keys = {(i, "ref") for i in adata_src.obs["batch"].cat.categories}

        tp = (
            TranslationProblem(adata_src, adata_tgt)
            .prepare(batch_key="batch", src_attr=src_attr, tgt_attr=tgt_attr, joint_attr=None)
            .solve()
        )
        for src, tgt in expected_keys:
            trans_forward = tp.translate(source=src, target=tgt, forward=True, alternative_attr=alternative_attr)
            assert trans_forward.shape == adata_tgt.obsm["X_pca"].shape
            trans_backward = tp.translate(source=src, target=tgt, forward=False, alternative_attr=alternative_attr)
            assert trans_backward.shape == adata_src[adata_src.obs["batch"] == "1"].obsm["X_pca"].shape

    @pytest.mark.fast()
    @pytest.mark.parametrize("forward", [True, False])
    @pytest.mark.parametrize("normalize", [True, False])
    def test_cell_transition_pipeline(
        self, adata_translation_split: Tuple[AnnData, AnnData], forward: bool, normalize: bool
    ):
        rng = np.random.RandomState(0)
        adata_src, adata_tgt = adata_translation_split
        tp = TranslationProblem(adata_src, adata_tgt)
        tp = tp.prepare(batch_key="batch", src_attr="emb_src", tgt_attr="emb_tgt", joint_attr="X_pca")
        mock_tmap_1 = np.abs(rng.randn(len(adata_src[adata_src.obs["batch"] == "1"]), len(adata_tgt)))
        mock_tmap_2 = np.abs(rng.randn(len(adata_src[adata_src.obs["batch"] == "2"]), len(adata_tgt)))

        solution = MockSolverOutput(mock_tmap_1 / np.sum(mock_tmap_1))
        tp["1", "ref"].set_solution(solution, overwrite=True)

        solution = MockSolverOutput(mock_tmap_2 / np.sum(mock_tmap_2))
        tp["2", "ref"].set_solution(solution, overwrite=True)

        result1 = tp.cell_transition(
            source="1",
            source_groups="celltype",
            target_groups="celltype",
            forward=forward,
            normalize=normalize,
        )

        result2 = tp.cell_transition(
            source="2",
            source_groups="celltype",
            target_groups="celltype",
            forward=forward,
            normalize=normalize,
        )

        assert isinstance(result1, pd.DataFrame)
        assert result1.shape == (3, 3)
        assert isinstance(result2, pd.DataFrame)
        assert result2.shape == (3, 3)
        with pytest.raises(AssertionError):
            pd.testing.assert_frame_equal(result1, result2)
