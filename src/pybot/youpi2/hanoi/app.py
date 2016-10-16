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

    STATE_INIT, STATE_READY, STATE_PICKING, STATE_PLACING, STATE_DONE = range(5)
    STATE_ABORT = -1
    STATE_NAMES = ['ABORT', 'INIT', 'READY', 'PICKING', 'PLACING', 'DONE']

    TOWER_X = 130
    TOWER_Y_DIST = 110
    BLOCK_HEIGHT = 27

    BLOCK_NAMES = ['A', 'B', 'C']   # A is the biggest one
    BLOCK_SIZES = [69, 55, 39]  # mm
    GRIPPER_STEPS_PER_MM = 92   # approx.
    GRIPPER_CLOSED_STEPS = -10006
    GRIPPER_RELEASE_MOVE = GRIPPER_STEPS_PER_MM * 10

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
    towers = [[0, 1, 2], [], []]      # we start from the left side => leftmost one is full

    step_num = 0
    # gripper_empty = True
    moved_block = None
    from_pose = to_pose = None

    start_x, start_y = TOWER_X, 0
    current_x = current_y = None

    ok_esc_line = None

    blk_closed_pos = [None] * 3

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
            level = max(len(self.towers[to_tower]), len(self.towers[from_tower]))
        else:
            # if we have to "skip over" the 3rd tower, the travel level is the one
            # above everybody
            level = max([len(t) for t in self.towers])

        # take into account the extra height of the carried block, if any
        return level if self.moved_block is None else level + 0.5

    def setup(self, **kwargs):
        self.arm.soft_hi_Z()

        self.kinematics = Kinematics(parent=self.logger)

        self.feed_pose = self._compute_pose(self.TOWER_X, 0, 0)

        self.state = self.STATE_INIT
        self.ok_esc_line = chr(CH_CANCEL) + (' ' * (self.pnl.width - 2)) + chr(CH_OK)

    def _ok_cancel(self, max_wait=None):
        self.pnl.write_at(self.ok_esc_line, line=1)
        return self.pnl.wait_for_key(valid=[Keys.OK, Keys.ESC], blink=True, max_wait=max_wait) == Keys.OK

    def _state_name(self, state):
        return self.STATE_NAMES[state + 1]

    # TODO make this work
    # def _open_gripper_for_block(self, blk_num):
    #     width = self.BLOCK_SIZES[blk_num] + 5
    #     steps = self.GRIPPER_CLOSED_STEPS + width * self.GRIPPER_STEPS_PER_MM
    #     self.arm.motor_goto({YoupiArm.MOTOR_GRIPPER: steps})
    #
    # def _release_block(self):
    #     self.arm.motor_move({YoupiArm.MOTOR_GRIPPER: self.GRIPPER_RELEASE_MOVE})

    def make_ready(self):
        self.pnl.clear()
        self.pnl.center_text_at('Set arm hands up', line=2)
        self.pnl.center_text_at('ESC:quit - OK:done', line=4)

        self.log_info('waiting for the arm be put in ready position...')
        if not self._ok_cancel():
            return self.STATE_ABORT

        self.pnl.clear()
        self.pnl.center_text_at('Already calibrated ?', line=2)
        self.pnl.center_text_at('ESC:no - OK:yes', line=4)

        self.log_info('is arm already calibrated ?')
        if self._ok_cancel():
            self.log_info('--> already calibrated')
            self.pnl.center_text_at('Moving home.', line=2)
            self.pnl.center_text_at('Please wait...', line=4)
            self.arm.go_home()
            self.arm.open_gripper()
        else:
            self.log_info('--> calibrating...')
            self.pnl.center_text_at('Calibrating.', line=2)
            self.pnl.center_text_at('Please wait...', line=4)
            self.arm.seek_origins()
            self.arm.calibrate_gripper()

        self.pnl.clear()
        self.pnl.center_text_at('Initial setup...', line=2)
        self.log_info('preparing tower...')

        feed_pose_hover = self._compute_pose(self.TOWER_X, 0, level=0.5)
        delta_shoulder = feed_pose_hover[YoupiArm.MOTOR_SHOULDER] - self.feed_pose[YoupiArm.MOTOR_SHOULDER]

        gripper_pos = self.arm.get_motor_positions()[YoupiArm.MOTOR_GRIPPER]
        self.log_info("gripper opened position : %d", gripper_pos)

        for i in range(3):
            blk_name = self.BLOCK_NAMES[i]

            self.arm.goto(self.feed_pose)

            self.pnl.clear()
            self.pnl.center_text_at('Give me block %s' % blk_name, line=2)
            self.pnl.center_text_at('ESC:quit - OK:done', line=4)
            self.log_info('waiting for block %s...', blk_name)
            if not self._ok_cancel(max_wait=120):
                return self.STATE_ABORT

            self.pnl.clear()

            self.log_info('.. picking...')
            self.pnl.center_text_at('Centering block...', line=2)
            self.arm.close_gripper()
            self.blk_closed_pos[i] = gripper_pos = self.arm.get_motor_positions()[YoupiArm.MOTOR_GRIPPER]
            self.log_info("gripper closed position for block %s : %d", self.BLOCK_NAMES[i], gripper_pos)
            self.arm.open_gripper()
            self.arm.motor_move({YoupiArm.MOTOR_SHOULDER: delta_shoulder})
            self.arm.rotate_hand_to(90)
            self.arm.motor_move({YoupiArm.MOTOR_SHOULDER: -delta_shoulder})
            self.arm.close_gripper()

            self.pnl.center_text_at('Installing block...', line=2)
            self.log_info('.. installing...')

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

            self.pnl.center_text_at('Next one...', line=2)
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
        self.pnl.center_text_at('ESC:quit - OK:go', line=4)

        self.log_info('ready - asking for what to do now...')
        if not self._ok_cancel(max_wait=120):
            self.log_info('.. abort requested')
            return self.STATE_ABORT

        return self.STATE_READY

    def start_solving(self):
        self.pnl.clear()
        self.pnl.center_text_at('Solving puzzle...', line=2)
        self.pnl.center_text_at('RED key to abort', line=4)
        self.pnl.set_leds([Keys.ESC])

        self.current_x, self.current_y = self.start_x, self.start_y

        return self.STATE_PICKING

    def _arm_action(self, meth, *args, **kwargs):
        """ Wraps an arm action request with the checking of the abort key use. """
        meth(*args, **kwargs)
        if Keys.ESC in self.pnl.get_keys():
            raise KeyboardInterrupt()

    def pick_block(self):
        from_side, to_side = (n * self.direction for n in self.sequence[self.step_num])
        from_tower, to_tower = from_side + 1, to_side + 1

        # compute the travel level depending on the current tower contents to fly to the target tower
        # without colliding
        travel_level = self.compute_travel_level(from_tower, to_tower)

        try:
            # climb at the right altitude before moving
            self._arm_action(self.arm.goto, self._compute_pose(self.current_x, self.current_y, travel_level))

            next_block = self.towers[from_tower][-1]
            blk_name = self.BLOCK_NAMES[next_block]

            # use a more natural tower numbering (i.e. starting from 1)
            human_friendly_from, human_friendly_to = from_tower + 1, to_tower + 1

            msg = "%s from %d to %d..." % (blk_name, human_friendly_from, human_friendly_to)
            self.pnl.center_text_at(msg, line=1)
            self.log_info('picking block %s from tower %d...', blk_name, human_friendly_from)

            still_to_do = len(self.sequence) - self.step_num
            if still_to_do > 1:
                msg = "Still %d moves to do" % still_to_do
            else:
                msg = "Last move !!"
            self.pnl.center_text_at(msg, line=2)

            from_level = len(self.towers[from_tower]) - 1  # levels are numbered from 0
            new_x, new_y = self.TOWER_X, self.TOWER_Y_DIST * from_side

            # move over the pick position
            self._arm_action(self.arm.goto, self._compute_pose(new_x, new_y, travel_level))
            # go down to the block
            self._arm_action(self.arm.goto, self._compute_pose(new_x, new_y, from_level))
            # pick it
            self._arm_action(self.arm.close_gripper)
            self.moved_block = self.towers[from_tower].pop()

            self.current_x, self.current_y = new_x, new_y
            return self.STATE_PLACING

        except KeyboardInterrupt:
            self.log_warning('ESC key pressed => abort')
            return self.STATE_ABORT

    def place_block(self):
        from_side, to_side = (n * self.direction for n in self.sequence[self.step_num])
        from_tower, to_tower = from_side + 1, to_side + 1
        human_friendly_to = to_tower + 1
        blk_name = self.BLOCK_NAMES[self.moved_block]

        # compute the travel level depending on the current tower contents to fly to the target tower
        # without colliding
        travel_level = self.compute_travel_level(from_tower, to_tower)

        try:
            # climb at the right altitude before moving
            self._arm_action(self.arm.goto, self._compute_pose(self.current_x, self.current_y, travel_level))

            # second half of the move : we bring the block to its destination tower
            self.log_info('placing block %s on tower %d...', blk_name, human_friendly_to)

            to_level = len(self.towers[to_tower])  # levels are numbered from 0
            new_x, new_y = self.TOWER_X, self.TOWER_Y_DIST * to_side

            # move over the drop position
            self._arm_action(self.arm.goto, self._compute_pose(new_x, new_y, travel_level))
            # go down to it
            self._arm_action(self.arm.goto, self._compute_pose(new_x, new_y, to_level))
            # release the block
            self._arm_action(self.arm.open_gripper)

            self.current_x, self.current_y = new_x, new_y

            # drop the block
            self.towers[to_tower].append(self.moved_block)
            self.moved_block = None

            self.step_num += 1
            return self.STATE_DONE if self.step_num == len(self.sequence) else self.STATE_PICKING

        except KeyboardInterrupt:
            self.log_warning('ESC key pressed => abort')
            return self.STATE_ABORT

    def again_or_enough(self):
        self.pnl.clear()
        self.pnl.center_text_at('Job done !!', line=2)
        self.log_info('Done')

        # final motion to the ready pose
        self.arm.goto(self._compute_pose(self.current_x, self.current_y, self.compute_travel_level(-1, +1)))
        self.arm.goto(self.ready_pose)

        self.pnl.center_text_at('ESC:quit - OK:again', line=4)
        self.log_info('asking for what to do now...')
        if self._ok_cancel(max_wait=120):
            self.step_num = 0
            self.direction = -self.direction
            return self.STATE_READY

        else:
            return self.STATE_ABORT

    def loop(self):
        self.log_info('current state: %s', self._state_name(self.state))

        if self.state == self.STATE_INIT:
            self.state = self.make_ready()
            return self.state == self.STATE_ABORT

        elif self.state == self.STATE_READY:
            self.state = self.start_solving()

        elif self.state == self.STATE_PICKING:
            self.state = self.pick_block()

            if self.state == self.STATE_ABORT:
                self.pnl.clear()
                self.pnl.center_text_at('Aborted !!', line=2)

        elif self.state == self.STATE_PLACING:
            self.state = self.place_block()

            if self.state == self.STATE_ABORT:
                self.pnl.clear()
                self.pnl.center_text_at('Aborted !!', line=2)

        elif self.state == self.STATE_DONE:
            self.state = self.again_or_enough()

        elif self.state == self.STATE_ABORT:
            return True

        else:
            raise RuntimeError('invalid state (%s)' % self.state)

    def teardown(self, exit_code):
        self.arm.open_gripper()
        self.arm.go_home()


def main():
    HanoiDemoApp().main()
