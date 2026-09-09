<?php
/**
 * Queued-episode detail view (Spec Section 8.2): every deliverable surfaced
 * with a direct, visible action to replace or regenerate it in place,
 * without needing to abort and restart the whole episode. Admin-only -
 * talent's own interaction is scoped to the My Show / Script Review screens.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Episode_Detail_Page {

	const SLUG = 'net-gain-episode-detail';

	public static function render() {
		$episode_id = isset( $_GET['episode_id'] ) ? (int) $_GET['episode_id'] : 0;
		$episode    = $episode_id ? get_post( $episode_id ) : null;

		if ( ! $episode || Net_Gain_CPT_Episode::POST_TYPE !== $episode->post_type ) {
			wp_die( 'Episode not found.' );
		}
		if ( ! Net_Gain_REST_Permissions::can_manage_episode( $episode_id ) ) {
			wp_die( 'You do not have permission to view this episode.' );
		}

		$show_id     = (int) $episode->post_parent;
		$episode_date = get_post_meta( $episode_id, 'ng_episode_date', true );
		$step_status = get_post_meta( $episode_id, 'ng_step_status', true ) ?: Net_Gain_Step_Status::default_status();
		$audio_id    = (int) get_post_meta( $episode_id, 'ng_audio_attachment_id', true );

		self::render_notices();
		?>
		<div class="wrap">
			<h1>Episode — <?php echo esc_html( $episode->post_title ); ?></h1>

			<h2>Script</h2>
			<p>Status: <strong><?php echo esc_html( $step_status['script_reviewed']['status'] ?? 'pending' ); ?></strong></p>
			<p>
				<a class="button" href="<?php echo esc_url( add_query_arg( array( 'page' => Net_Gain_Script_Review_Page::SLUG, 'episode_id' => $episode_id ), admin_url( 'admin.php' ) ) ); ?>">Open Script Review</a>
				<?php self::render_trigger_button( $show_id, $episode_date, 'generate_script', 'script_generated', $step_status, 'Generate Script', 'Regenerate Script' ); ?>
			</p>

			<h2>Audio</h2>
			<?php if ( $audio_id ) : ?>
				<p><a href="<?php echo esc_url( wp_get_attachment_url( $audio_id ) ); ?>" target="_blank" rel="noopener">Listen to master audio file</a></p>
			<?php else : ?>
				<p>No audio uploaded yet — talent uploads from the My Show screen.</p>
			<?php endif; ?>

			<h2>Metadata</h2>
			<p>Status: <strong><?php echo esc_html( $step_status['metadata_generated']['status'] ?? 'pending' ); ?></strong> — deliberately generated close to publish time, not at finalization (see Spec Section 8.1).</p>

			<h2>Images</h2>
			<p>Status: <strong><?php echo esc_html( $step_status['images_rendered']['status'] ?? 'pending' ); ?></strong></p>
			<p><?php self::render_trigger_button( $show_id, $episode_date, 'generate_images', 'images_rendered', $step_status, 'Generate Images', 'Regenerate Images' ); ?></p>

			<h2>Publishing</h2>
			<p>Captivate: <strong><?php echo esc_html( $step_status['captivate_published']['status'] ?? 'pending' ); ?></strong></p>
			<p><?php self::render_trigger_button( $show_id, $episode_date, 'publish_captivate', 'captivate_published', $step_status, 'Publish to Captivate', 'Re-publish to Captivate' ); ?></p>
			<p class="description">Website and YouTube publishing aren't built yet (Phases 6 and 9).</p>
		</div>
		<?php
	}

	private static function render_trigger_button( $show_id, $episode_date, $action_key, $step_key, $step_status, $label_generate, $label_regenerate ) {
		$blocker = Net_Gain_Step_Status::unmet_prerequisite( $step_key, $step_status );
		if ( $blocker ) {
			printf(
				'<button type="button" class="button" disabled title="Requires %1$s to be done first">%2$s</button>',
				esc_attr( $blocker ),
				esc_html( $label_generate )
			);
			return;
		}

		$current = $step_status[ $step_key ]['status'] ?? 'pending';
		$is_done = in_array( $current, array( 'done', 'degraded' ), true );
		?>
		<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="display:inline;">
			<?php wp_nonce_field( 'ng_enqueue_action', 'ng_enqueue_action_nonce' ); ?>
			<input type="hidden" name="action" value="ng_enqueue_action">
			<input type="hidden" name="show_id" value="<?php echo esc_attr( $show_id ); ?>">
			<input type="hidden" name="episode_action" value="<?php echo esc_attr( $action_key ); ?>">
			<input type="hidden" name="episode_date" value="<?php echo esc_attr( $episode_date ); ?>">
			<input type="hidden" name="force" value="<?php echo esc_attr( $is_done ? '1' : '0' ); ?>">
			<button type="submit" class="button"><?php echo esc_html( $is_done ? $label_regenerate : $label_generate ); ?></button>
		</form>
		<?php
	}

	private static function render_notices() {
		if ( isset( $_GET['ng_notice'] ) && 'action_queued' === $_GET['ng_notice'] ) {
			echo '<div class="notice notice-success is-dismissible"><p>Queued — the tick loop will pick this up on its next pass.</p></div>';
		}
	}
}
