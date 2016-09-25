# -*- coding: utf-8 -*-

from pybot.youpi2.app import YoupiApplication
from pybot.youpi2.ctlpanel import Keys
from pybot.youpi2.ctlpanel.widgets import CH_OK, CH_CANCEL
from pybot.youpi2.model import YoupiArm

try:
    from __version__ import version
except ImportError:
    version = "?"

__author__ = 'Eric Pascual'


class HanoiDemoApp(YoupiApplication):
    NAME = 'demo-hanoi'
    TITLE = "Hanoi towers demo"
    VERSION = version

    DEFAULT_BASE_ANGLE = 25
    HAND_POSITION = 90

    STATE_INIT, STATE_READY, STATE_SOLVING, STATE_DONE = range(4)

    base_angle = DEFAULT_BASE_ANGLE

    positions = [
        {YoupiArm.MOTOR_SHOULDER: 84, YoupiArm.MOTOR_ELBOW: 43, YoupiArm.MOTOR_WRIST: 46},
        {YoupiArm.MOTOR_SHOULDER: 76, YoupiArm.MOTOR_ELBOW: 50, YoupiArm.MOTOR_WRIST: 48},
        {YoupiArm.MOTOR_SHOULDER: 68, YoupiArm.MOTOR_ELBOW: 56, YoupiArm.MOTOR_WRIST: 49},
    ]

    feed_pose = positions[0].copy()
    start_pose = positions[-1].copy()

    transport_motor_pos = {YoupiArm.MOTOR_SHOULDER: 60}

    sequence = [
        # (side, level) to (side, level)
        ((-1, 2), (1, 0)),
        ((-1, 1), (0, 0)),
        ((1, 0), (0, 1)),
        ((-1, 0), (1, 0)),
        ((0, 1), (-1, 0)),
        ((0, 0), (1, 1)),
        ((-1, 0), (1, 2)),
    ]

    direction = 1

    step_num = 0
    with_block = False
    from_pose = to_pose = None

    ok_esc_line = None

    state = STATE_INIT

    def add_custom_arguments(self, parser):
        parser.add_argument('--base-angle', default=self.DEFAULT_BASE_ANGLE)

    def setup(self, base_angle=DEFAULT_BASE_ANGLE, **kwargs):
        self.base_angle = base_angle
        self.arm.soft_hi_Z()
        self.state = self.STATE_INIT
        self.ok_esc_line = chr(CH_CANCEL) + (' ' * (self.pnl.width - 2)) + chr(CH_OK)

    def _compute_pose(self, side, level):
        pose = self.positions[level]
        pose[YoupiArm.MOTOR_BASE] = side * self.direction * self.base_angle
        return pose

    def _ok_cancel(self):
        self.pnl.write_at(self.ok_esc_line, line=1)
        return self.pnl.wait_for_key(valid=[Keys.OK, Keys.ESC], blink=True) == Keys.OK

    def loop(self):
        if self.state == self.STATE_INIT:
            self.pnl.clear()
            self.pnl.center_text_at('Set arm hands up', line=2)
            self.pnl.center_text_at('OK: go - ESC: quit', line=4)

            if not self._ok_cancel():
                return 1

            self.pnl.clear()
            self.pnl.center_text_at('Already calibrated ?', line=2)
            self.pnl.center_text_at('OK: yes - ESC: no', line=4)

            if self._ok_cancel():
                self.pnl.center_text_at('Moving home.', line=2)
                self.pnl.center_text_at('Please wait...', line=4)
                self.arm.go_home()
                self.arm.open_gripper()
            else:
                self.pnl.center_text_at('Calibrating.', line=2)
                self.pnl.center_text_at('Please wait...', line=4)
                self.arm.seek_origins()
                self.arm.calibrate_gripper()

            self.pnl.clear()
            self.pnl.center_text_at('Tower initial', line=2)
            self.pnl.center_text_at('setup...', line=3)

            blk_nums = ['1st', '2nd', '3rd']
            for i in range(3):
                self.arm.goto(self.feed_pose)
                self.pnl.clear()
                self.pnl.center_text_at('Give me %s block' % blk_nums[i], line=2)
                self.pnl.center_text_at('OK: go - ESC: quit', line=4)
                if not self._ok_cancel():
                    return 1

                self.pnl.clear()
                self.pnl.center_text_at('Preparing tower', line=2)

                self.arm.close_gripper()
                self.arm.motor_goto(self.transport_motor_pos)

                pose = self._compute_pose(-1, i)
                self.arm.motor_goto({YoupiArm.MOTOR_BASE: pose[YoupiArm.MOTOR_BASE]})
                self.arm.goto(pose)
                self.arm.open_gripper()
                self.arm.motor_goto(self.transport_motor_pos)
                self.arm.go_home([YoupiArm.MOTOR_BASE])

            self.pnl.clear()
            self.pnl.center_text_at('Back home...', line=2)
            self.arm.go_home()

            self.pnl.clear()
            self.pnl.center_text_at('Ready.', line=2)
            self.pnl.center_text_at('OK: go - ESC: quit', line=4)

            if not self._ok_cancel():
                return 1

            self.state = self.STATE_READY

        elif self.state == self.STATE_READY:
            self.clear_screen()
            self.pnl.center_text_at('Solving puzzle...', line=3)

            self.arm.goto(self.start_pose)
            self.arm.rotate_hand_to(self.HAND_POSITION)

            self.state = self.STATE_SOLVING

        elif self.state == self.STATE_SOLVING:
            self.pnl.center_text_at("Steps to go : %d" % (len(self.sequence) - self.step_num), line=3)

            self.arm.motor_goto(self.transport_motor_pos)

            step_from, step_to = self.sequence[self.step_num]

            if self.with_block:
                pose = self._compute_pose(*step_to)
                self.arm.goto({YoupiArm.MOTOR_BASE: pose[YoupiArm.MOTOR_BASE]})
                self.arm.goto(pose)
                self.arm.open_gripper()

                self.with_block = False

                self.step_num += 1
                if self.step_num == len(self.sequence):
                    self.state = self.STATE_DONE

            else:
                pose = self._compute_pose(*step_from)
                self.arm.goto({YoupiArm.MOTOR_BASE: pose[YoupiArm.MOTOR_BASE]})
                self.arm.goto(pose)
                self.arm.close_gripper()

                self.with_block = True

        elif self.state == self.STATE_DONE:
            self.pnl.clear()
            self.pnl.center_text_at('Job done !!', line=2)

            self.arm.go_home(YoupiArm.MOTOR_BASE)
            self.arm.go_home()

            self.pnl.center_text_at('OK: redo - ESC: quit', line=4)
            if self._ok_cancel():
                self.step_num = 0
                self.direction = -self.direction
                self.state = self.STATE_READY

            else:
                return 1

        else:
            raise RuntimeError('invalid state (%s)' % self.state)

    def teardown(self, exit_code):
        self.arm.open_gripper()
        self.arm.go_home()


def main():
    HanoiDemoApp().main()
