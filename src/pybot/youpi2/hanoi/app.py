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
    STATE_ABORT = -1

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

    # global direction of the move (start with a left to right tower move first)
    direction = 1

    # towers are numbered from -1 to 1 so that it is easier to do the symmetry for
    # reversing the global move direction
    # (the sequence is defined for the initial direction)
    sequence = [
        # from side, to side
        (-1, 1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (-1, 1)
    ]

    # number of blocks in each position
    tower_heights = [3, 0, 0]       # we start from the left side => leftmost one is full

    step_num = 0
    gripper_empty = True
    from_pose = to_pose = None

    start_x, start_y = TOWER_X, 0
    current_x = current_y = None

    ok_esc_line = None

    state = STATE_INIT

    def _compute_pose(self, x, y, level, hand_rot=0):
        angles = self.kinematics.ik(x, y, self.BLOCK_HEIGHT * (level + 0.5))
        pose = {i: a for i, a in enumerate(angles)}

        pose[YoupiArm.MOTOR_HAND_ROT] = pose[YoupiArm.MOTOR_BASE] + hand_rot
        return pose

    def compute_travel_level(self, from_tower, to_tower):
        """ Returns the level (starting from 0) at which the gripper must travel
        not to collide with towers. """
        if abs(to_tower - from_tower) == 1:
            # from and to positions are contiguous => it is the highest of both
            level = max(self.tower_heights[to_tower], self.tower_heights[from_tower])
        else:
            # if we have to "skip over" the 3rd tower, the travel level is the one
            # above every body
            level = max(self.tower_heights)

        # take into account the extra height of the carried block, if any
        return (level - 0.5) if self.gripper_empty else (level + 0.5)

    def setup(self, **kwargs):
        self.arm.soft_hi_Z()

        self.kinematics = Kinematics(parent=self.logger)

        self.feed_pose = self._compute_pose(self.TOWER_X, 0, 0)

        self.state = self.STATE_INIT
        self.ok_esc_line = chr(CH_CANCEL) + (' ' * (self.pnl.width - 2)) + chr(CH_OK)

    def _ok_cancel(self):
        self.pnl.write_at(self.ok_esc_line, line=1)
        return self.pnl.wait_for_key(valid=[Keys.OK, Keys.ESC], blink=True) == Keys.OK

    def make_ready(self):
        self.pnl.clear()
        self.pnl.center_text_at('Set arm hands up', line=2)
        self.pnl.center_text_at('ESC: quit - OK: go', line=4)

        if not self._ok_cancel():
            return self.STATE_ABORT

        self.pnl.clear()
        self.pnl.center_text_at('Already calibrated ?', line=2)
        self.pnl.center_text_at('ESC: no - OK: yes', line=4)

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
        self.pnl.center_text_at('Initial setup...', line=2)

        feed_pose_hover = self._compute_pose(self.TOWER_X, 0, level=0.5)
        delta_shoulder = feed_pose_hover[YoupiArm.MOTOR_SHOULDER] - self.feed_pose[YoupiArm.MOTOR_SHOULDER]

        blk_nums = ['1st', '2nd', '3rd']
        for i in range(3):
            self.arm.goto(self.feed_pose)

            self.pnl.clear()
            self.pnl.center_text_at('Give me %s block' % blk_nums[i], line=2)
            self.pnl.center_text_at('ESC: quit - OK: go', line=4)
            if not self._ok_cancel():
                return self.STATE_ABORT

            self.pnl.clear()

            self.pnl.center_text_at('Centering block...', line=2)
            self.arm.close_gripper()
            self.arm.open_gripper()
            self.arm.motor_move({YoupiArm.MOTOR_SHOULDER: delta_shoulder})
            self.arm.rotate_hand_to(90)
            self.arm.motor_move({YoupiArm.MOTOR_SHOULDER: -delta_shoulder})
            self.arm.close_gripper()

            self.pnl.center_text_at('Installing block...', line=2)

            self.arm.goto(self._compute_pose(self.TOWER_X, 0, level=i + 0.5, hand_rot=90))

            pose_hover = self._compute_pose(self.TOWER_X, -self.TOWER_Y_DIST, level=i + 0.5, hand_rot=90)
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
        self.pnl.center_text_at('ESC: quit - OK: go', line=4)

        if not self._ok_cancel():
            return self.STATE_ABORT

        return self.STATE_READY

    def start_solving(self):
        self.clear_screen()
        self.pnl.center_text_at('Solving puzzle...', line=3)

        self.current_x, self.current_y = self.start_x, self.start_y

        return self.STATE_SOLVING

    def move_things(self):
        from_side, to_side = (n * self.direction for n in self.sequence[self.step_num])
        from_tower, to_tower = from_side + 1, to_side + 1

        # use a more natural tower numbering (i.e. starting from 1)
        self.pnl.center_text_at("Move from %d to %d..." % (from_tower + 1, to_tower + 1))
        still_to_do = len(self.sequence) - self.step_num
        if still_to_do > 1:
            self.pnl.center_text_at("Still %d moves to do" % still_to_do, line=4)
        else:
            self.pnl.center_text_at("Last move !!", line=4)

        # raise enough depending on the current tower heights to fly to the target tower
        # without colliding
        travel_level = self.compute_travel_level(from_tower, to_tower)
        self.arm.goto(self._compute_pose(self.current_x, self.current_y, travel_level))

        if self.gripper_empty:
            # first half of the move : we go and pick the block to move

            from_level = self.tower_heights[from_tower] - 1     # levels are numbered from 0
            new_x, new_y = self.TOWER_X, self.TOWER_Y_DIST * from_side

            # move over the pick position
            self.arm.goto(self._compute_pose(new_x, new_y, travel_level))
            # go down to the position
            self.arm.goto(self._compute_pose(new_x, new_y, from_level))
            # pick the block
            self.arm.close_gripper()

            self.current_x, self.current_y = new_x, new_y

            # since we pick a block, the tower is now one unit smaller
            self.tower_heights[from_tower] -= 1
            # and we are carrying something
            self.gripper_empty = False

        else:
            # second half of the move : we bring the block to its destination tower

            to_level = self.tower_heights[to_tower]     # levels are numbered from 0
            new_x, new_y = self.TOWER_X, self.TOWER_Y_DIST * to_side

            # move over the drop position
            self.arm.goto(self._compute_pose(new_x, new_y, travel_level))
            # go down to the position
            self.arm.goto(self._compute_pose(new_x, new_y, to_level))
            # release the block
            self.arm.open_gripper()

            self.current_x, self.current_y = new_x, new_y

            # the destination tower is not une unit taller
            self.tower_heights[to_tower] += 1

            # we are carrying something no more
            self.gripper_empty = True

            self.step_num += 1
            if self.step_num == len(self.sequence):
                return self.STATE_DONE

        # we are not finished => stay in the current state
        return self.state

    def again_or_enough(self):
        self.pnl.clear()
        self.pnl.center_text_at('Job done !!', line=2)

        # final motion to the ready pose
        self.arm.goto(self._compute_pose(self.current_x, self.current_y, self.compute_travel_level(-1, +1)))
        self.arm.goto(self.ready_pose)

        self.pnl.center_text_at('ESC: end - OK: again', line=4)
        if self._ok_cancel():
            self.step_num = 0
            self.direction = -self.direction
            return self.STATE_READY

        else:
            return self.STATE_ABORT

    def loop(self):
        if self.state == self.STATE_INIT:
            self.state = self.make_ready()
            return self.state == self.STATE_ABORT

        elif self.state == self.STATE_READY:
            self.state = self.start_solving()

        elif self.state == self.STATE_SOLVING:
            self.state = self.move_things()

        elif self.state == self.STATE_DONE:
            self.state = self.again_or_enough()
            return self.state == self.STATE_ABORT

        else:
            raise RuntimeError('invalid state (%s)' % self.state)

    def teardown(self, exit_code):
        self.arm.open_gripper()
        self.arm.go_home()


def main():
    HanoiDemoApp().main()
