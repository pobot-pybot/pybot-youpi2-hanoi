# -*- coding: utf-8 -*-

from pybot.youpi2.app import YoupiApplication
from pybot.youpi2.ctlpanel import Keys
from pybot.youpi2.ctlpanel.widgets import CH_OK, CH_CANCEL
from pybot.youpi2.model import YoupiArm
from pybot.youpi2.kin import Kinematics

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

    STATE_INIT, STATE_READY, STATE_SOLVING, STATE_DONE = range(4)

    TOWER_X = 130
    TOWER_Y_DIST = 110
    BLOCK_HEIGHT = 27

    feed_pose = None
    kinematics = None

    ready_pose = {
        YoupiArm.MOTOR_BASE: 0,
        YoupiArm.MOTOR_SHOULDER: 0,
        YoupiArm.MOTOR_ELBOW: 45,
        YoupiArm.MOTOR_WRIST: 45,
        YoupiArm.MOTOR_HAND_ROT: 0
    }

    # transport_sub_pose = None

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
    carrying = False
    from_pose = to_pose = None

    start_x, start_y, transport_level = TOWER_X, 0, 2.5
    current_x = current_y = None

    ok_esc_line = None

    state = STATE_INIT

    def _compute_pose(self, x, y, level, hand_rot=0):
        angles = self.kinematics.ik(x, y, self.BLOCK_HEIGHT * (level + 0.5))
        pose = {i: a for i, a in enumerate(angles)}

        pose[YoupiArm.MOTOR_HAND_ROT] = pose[YoupiArm.MOTOR_BASE] + hand_rot
        return pose

    def setup(self, **kwargs):
        self.arm.soft_hi_Z()

        self.kinematics = Kinematics(parent=self.logger)

        self.feed_pose = self._compute_pose(self.TOWER_X, 0, 0)

        self.state = self.STATE_INIT
        self.ok_esc_line = chr(CH_CANCEL) + (' ' * (self.pnl.width - 2)) + chr(CH_OK)

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
            self.pnl.center_text_at('Tower setup...', line=2)

            feed_pose_hover = self._compute_pose(self.TOWER_X, 0, level=0.5)
            delta_shoulder = feed_pose_hover[YoupiArm.MOTOR_SHOULDER] - self.feed_pose[YoupiArm.MOTOR_SHOULDER]

            blk_nums = ['1st', '2nd', '3rd']
            for i in range(3):
                self.arm.goto(self.feed_pose)

                self.pnl.clear()
                self.pnl.center_text_at('Give me %s block' % blk_nums[i], line=2)
                self.pnl.center_text_at('OK: go - ESC: quit', line=4)
                if not self._ok_cancel():
                    return 1

                self.pnl.clear()

                self.pnl.center_text_at('Centering block...', line=2)
                self.arm.close_gripper()
                self.arm.open_gripper()
                self.arm.motor_move({YoupiArm.MOTOR_SHOULDER: delta_shoulder})
                self.arm.rotate_hand_to(90)
                self.arm.motor_move({YoupiArm.MOTOR_SHOULDER: -delta_shoulder})
                self.arm.close_gripper()

                self.pnl.center_text_at('Assembling tower...', line=2)

                self.arm.goto(self._compute_pose(self.TOWER_X, 0, level=i+0.5, hand_rot=90))

                pose_hover = self._compute_pose(self.TOWER_X, -self.TOWER_Y_DIST, level=i+0.5, hand_rot=90)
                self.arm.goto(pose_hover)

                pose = self._compute_pose(self.TOWER_X, -self.TOWER_Y_DIST, level=i, hand_rot=90)
                self.arm.goto({
                    YoupiArm.MOTOR_BASE: pose[YoupiArm.MOTOR_BASE],
                    YoupiArm.MOTOR_HAND_ROT: pose[YoupiArm.MOTOR_HAND_ROT]
                })
                self.arm.goto(pose)

                self.arm.open_gripper()

                self.arm.goto(pose_hover)
                if i == 2:
                    break

                pose = self._compute_pose(self.TOWER_X, 0, level=0)
                self.arm.goto({
                    YoupiArm.MOTOR_BASE: pose[YoupiArm.MOTOR_BASE],
                    YoupiArm.MOTOR_HAND_ROT: pose[YoupiArm.MOTOR_HAND_ROT]
                })
                self.arm.goto(pose)

            self.pnl.clear()
            self.pnl.center_text_at('Almost ready...', line=2)
            self.arm.goto(self.ready_pose)

            self.pnl.clear()
            self.pnl.center_text_at('Ready.', line=2)
            self.pnl.center_text_at('OK: go - ESC: quit', line=4)

            if not self._ok_cancel():
                return 1

            self.state = self.STATE_READY

        elif self.state == self.STATE_READY:
            self.clear_screen()
            self.pnl.center_text_at('Solving puzzle...', line=3)

            self.current_x, self.current_y = self.start_x, self.start_y

            self.state = self.STATE_SOLVING

        elif self.state == self.STATE_SOLVING:
            self.pnl.center_text_at("Remaining moves : %d" % (len(self.sequence) - self.step_num), line=3)

            self.arm.goto(self._compute_pose(self.current_x, self.current_y, self.transport_level))

            step_from, step_to = self.sequence[self.step_num]

            if self.carrying:
                side, level = step_to
                new_x, new_y = self.TOWER_X, self.TOWER_Y_DIST * side * self.direction

                # move over the drop position
                self.arm.goto(self._compute_pose(new_x, new_y, self.transport_level))
                # go down to the position
                self.arm.goto(self._compute_pose(new_x, new_y, level))
                # release the block
                self.arm.open_gripper()

                self.current_x, self.current_y = new_x, new_y
                self.carrying = False

                self.step_num += 1
                if self.step_num == len(self.sequence):
                    self.state = self.STATE_DONE

            else:
                side, level = step_from
                new_x, new_y = self.TOWER_X, self.TOWER_Y_DIST * side * self.direction

                # move over the pick position
                self.arm.goto(self._compute_pose(new_x, new_y, self.transport_level))
                # go down to the position
                self.arm.goto(self._compute_pose(new_x, new_y, level))
                # pick the block
                self.arm.close_gripper()

                self.current_x, self.current_y = new_x, new_y
                self.carrying = True

        elif self.state == self.STATE_DONE:
            self.pnl.clear()
            self.pnl.center_text_at('Job done !!', line=2)

            # final motion to the ready pose
            self.arm.goto(self._compute_pose(self.current_x, self.current_y, self.transport_level))
            self.arm.goto(self.ready_pose)

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
