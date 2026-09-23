"""下载/同步流水线核心边界校验：info.json → 飞书 ``视频指标快照`` 表 row 载荷。

覆盖路径（对应根目录 ``download_bili_following_latest.py`` 的收尾阶段）：

1. ``metric_snapshot_from_info(info)`` 从 B 站 ``raw.data.stat`` 提取
   播放量 / 点赞量 / 投币数 / 收藏数 / 分享数 / 评论数 / 弹幕数；
2. ``batch_create_metric_snapshots(config, items)`` 组装
   ``+record-batch-create --json @<payload>`` 命令，把
   关联视频 / 快照时间 / 播放量 / 点赞量 / 投币数 / 收藏数 / 分享数 /
   评论数 / 弹幕数 / 粉丝数快照 / 备注 这些列以固定顺序写入飞书。

这正是根目录手工探针 ``_test_snapshot.py`` 手写 payload 直接 upsert 到
``tblMVVv7wijHCULu``（视频指标快照）的行结构；区别是：

- 手工脚本要求已登录 ``lark-cli``、真实 base_token / record_id，
  在 CI 与离线环境下不可复现；
- 本用例把外部依赖 (``run_lark``) 换成最小可注入替身，
  只断言"发往飞书的字段顺序 + 行值"这一稳定边界，不改动业务代码；
- 因此 ``pytest tests/`` 会真正采集并运行本用例，
  而 ``_test_*.py`` 因下划线前缀不会被采集，只是虚假信号。

其余 ``_test_*.py`` 保留为手工探针，见文末注释。
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

import download_bili_following_latest as base


# 与业务代码 download_bili_following_latest.batch_create_metric_snapshots
# 中定义的 fields 顺序一致；一旦字段顺序漂移，本用例应给出失败信号。
EXPECTED_SNAPSHOT_FIELDS = [
    "关联视频",
    "快照时间",
    "播放量",
    "点赞量",
    "投币数",
    "收藏数",
    "分享数",
    "评论数",
    "弹幕数",
    "粉丝数快照",
    "备注",
]

CONFIG = {
    "base_token": "fakeBaseTokenForOfflineTest",
    "tables": {"video_metric_snapshots": {"table_id": "tblMVVv7wijHCULu"}},
}


def _fake_info(with_stat: bool) -> dict:
    """构造与本地 info.json 结构一致的替身（无网络、无磁盘）。"""
    raw_data: dict = {
        "bvid": "BVTEST",
        "aid": 12345,
        "title": "测试视频",
    }
    if with_stat:
        raw_data["stat"] = {
            "view": 1234,
            "like": 56,
            "coin": 7,
            "favorite": 8,
            "share": 9,
            "reply": 10,
            "danmaku": 11,
        }
    return {"id": "BVTEST", "display_id": "BVTEST", "raw": {"data": raw_data}}


class VideoMetricSnapshotFlowTests(unittest.TestCase):
    """一次覆盖一个稳定边界：info.json → 视频指标快照 row → run_lark 载荷。"""

    def _spy_run_lark(self, captured: dict, record_ids: list[str]):
        """最小可注入替身：拦截 lark-cli 调用，把临时 payload 文件读回内存。

        真实的 ``batch_create_metric_snapshots`` 会把 payload 写到
        ``ROOT/.tmp-lark/<uuid>.json``，然后以 ``--json @<相对路径>`` 传给
        ``run_lark``。因为 finally 里的 ``payload_path.unlink`` 在 mock 返回后
        才执行，我们可以在替身内部安全读取。
        """

        def _fake(config, args, *, timeout=60):
            self.assertEqual(config["base_token"], CONFIG["base_token"])
            self.assertIn("+record-batch-create", args)
            json_idx = args.index("--json")
            payload_ref = args[json_idx + 1]
            self.assertTrue(
                payload_ref.startswith("@"),
                f"--json 参数应为 @<相对路径>，实际为 {payload_ref!r}",
            )
            relative = payload_ref[1:].replace("\\", "/")
            payload_file = base.ROOT.joinpath(*relative.split("/"))
            captured["payload"] = json.loads(payload_file.read_text(encoding="utf-8"))
            captured["args"] = list(args)
            captured["timeout"] = timeout
            captured["table_id"] = args[args.index("--table-id") + 1]
            return {"data": {"record_id_list": list(record_ids)}}

        return _fake

    def test_info_stat_maps_to_feishu_video_metric_row(self):
        """B 站 info.raw.data.stat 应完整映射为飞书视频指标快照 row。"""
        info = _fake_info(with_stat=True)
        metrics = base.metric_snapshot_from_info(info)
        self.assertIsNotNone(metrics, "有 stat 时 metric_snapshot_from_info 不应返回 None")
        self.assertEqual(
            {k: metrics[k] for k in ("播放量", "点赞量", "投币数", "收藏数", "分享数", "评论数", "弹幕数")},
            {"播放量": 1234, "点赞量": 56, "投币数": 7, "收藏数": 8, "分享数": 9, "评论数": 10, "弹幕数": 11},
            "B 站 stat 字段与飞书视频指标快照列的映射不能变",
        )
        # 备注列写入数据来源，方便回溯；粉丝数快照由博主侧填，视频下载不填。
        self.assertEqual(metrics["备注"], "source=metadata.raw.data.stat")
        self.assertIsNone(metrics["粉丝数快照"])

        captured: dict = {}
        items = [
            {
                "video_record_id": "recVidTest",
                "bvid": "BVTEST",
                "metrics": metrics,
                "metrics_path": "downloads/videos/1/BVTEST/metrics-snapshot.json",
                "snapshot_time": "2026-08-04 17:00:00",
            }
        ]

        with mock.patch.object(base, "run_lark", side_effect=self._spy_run_lark(captured, ["recSnap1"])):
            created = base.batch_create_metric_snapshots(CONFIG, items)

        self.assertEqual(created, ["recSnap1"], "batch_create_metric_snapshots 应回传飞书 record_id")
        self.assertEqual(captured["table_id"], CONFIG["tables"]["video_metric_snapshots"]["table_id"])
        self.assertEqual(captured["timeout"], 120)

        payload = captured["payload"]
        self.assertEqual(payload["fields"], EXPECTED_SNAPSHOT_FIELDS, "视频指标快照字段顺序不能漂移")
        self.assertEqual(len(payload["rows"]), 1)
        row = payload["rows"][0]
        # row[0] 关联视频：link 字段，[{"id": <video_record_id>}]
        self.assertEqual(row[0], [{"id": "recVidTest"}])
        # row[1] 快照时间
        self.assertEqual(row[1], "2026-08-04 17:00:00")
        # row[2..8] 播放量 / 点赞量 / 投币数 / 收藏数 / 分享数 / 评论数 / 弹幕数
        self.assertEqual(row[2:9], [1234, 56, 7, 8, 9, 10, 11])
        # row[9] 粉丝数快照：视频下载不下发，保持 None
        self.assertIsNone(row[9])
        # row[10] 备注：应包含 BVID 与本地 metrics-snapshot 路径，方便人工回溯
        self.assertIn("BVID=BVTEST", row[10])
        self.assertIn("metrics-snapshot.json", row[10])

    def test_missing_stat_short_circuits_without_lark_call(self):
        """info 未携带 raw.data.stat 时，本条 item 应被跳过且不触发 lark-cli 调用。

        覆盖的是"降级不炸"这一稳定行为：视频元数据缺 stat 是常见情况
        （例如 B 站返回不完整），流水线不能因此给飞书写空快照或抛错。
        """
        info = _fake_info(with_stat=False)
        self.assertIsNone(base.metric_snapshot_from_info(info))

        calls: list = []

        def _spy(*args, **kwargs):
            calls.append((args, kwargs))
            return {"data": {"record_id_list": []}}

        items = [
            {
                "video_record_id": "recVidTest",
                "bvid": "BVTEST",
                "metrics": None,
                "metrics_path": "downloads/videos/1/BVTEST/metrics-snapshot.json",
                "snapshot_time": "2026-08-04 17:00:00",
            }
        ]
        with mock.patch.object(base, "run_lark", side_effect=_spy):
            created = base.batch_create_metric_snapshots(CONFIG, items)

        self.assertEqual(created, [])
        self.assertEqual(calls, [], "metrics=None 时不应向 lark-cli 发送写入请求")


# 手工探针脚本清单（保留但不进入 pytest 采集，因为它们需要真实登录态 / 网络）：
# - _test_snapshot.py：向飞书 tblMVVv7wijHCULu（视频指标快照）真实 upsert 一条记录，
#   与本用例覆盖同一 payload 形状；已由本文件在离线侧取代，但作为端到端 live 检查仍可手动执行。
# - _test_lark.py：调用 lark-cli base +record-list 拉取真实表数据。
# - _test_cdp_login.py / _test_douyin_*.py / _test_xhs_access.py：
#   依赖已登录 Chrome / CDP 9222 端口，抖音与小红书抓取前的连通性检查。
# - _test_platforms.py：仅检查 download_*.py / sync_*.py 脚本文件是否存在，
#   属于安装完整性冒烟，与流水线业务边界无关。
# 这些脚本保持 ``_test_`` 前缀 = 有意不被 pytest 采集，仅作为开发者手动运行入口。


if __name__ == "__main__":
    unittest.main()
