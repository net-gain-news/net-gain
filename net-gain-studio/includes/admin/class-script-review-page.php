<?php
/**
 * Human script review (Spec Section 5.2). The final version gets full
 * screen width - a side-by-side draft/final layout was tried and explicitly
 * rejected as insufficient for genuine editing - with the AI draft available
 * behind a collapsed toggle for reference only.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Script_Review_Page {

	const SLUG = 'net-gain-script-review';

	public static function render() {
		$episode_id = isset( $_GET['episode_id'] ) ? (int) $_GET['episode_id'] : 0;
		$episode    = $episode_id ? get_post( $episode_id ) : null;

		if ( ! $episode || Net_Gain_CPT_Episode::POST_TYPE !== $episode->post_type ) {
			wp_die( 'Episode not found.' );
		}
		if ( ! Net_Gain_REST_Permissions::can_act_on_episode_finalization( $episode_id ) ) {
			wp_die( 'You do not have permission to review this episode.' );
		}

		$draft = get_post_meta( $episode_id, 'ng_script_draft', true );
		$final = get_post_meta( $episode_id, 'ng_script_final', true );
		$step_status = get_post_meta( $episode_id, 'ng_step_status', true );
		$review_status = $step_status['script_reviewed']['status'] ?? 'pending';
		$review_note   = $step_status['script_reviewed']['note'] ?? '';

		self::render_notices();
		?>
		<div class="wrap ng-script-review">
			<h1>Script Review — <?php echo esc_html( $episode->post_title ); ?></h1>

			<?php if ( 'degraded' === $review_status ) : ?>
				<div class="notice notice-warning"><p><strong>Flagged for a second look:</strong> <?php echo esc_html( $review_note ); ?> — this doesn't block anything, it's just worth confirming this wasn't an accidental zero-edit save.</p></div>
			<?php endif; ?>

			<p>
				<button type="button" class="button" id="ng-toggle-draft">Show AI draft</button>
			</p>
			<div id="ng-ai-draft" style="display:none; background:#f6f7f7; border:1px solid #dcdcde; padding:16px; margin-bottom:20px; white-space:pre-wrap;"><?php echo esc_html( $draft ); ?></div>

			<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
				<?php wp_nonce_field( 'ng_save_script_review', 'ng_save_script_review_nonce' ); ?>
				<input type="hidden" name="action" value="ng_save_script_review">
				<input type="hidden" name="episode_id" value="<?php echo esc_attr( $episode_id ); ?>">

				<textarea name="script_final" style="width:100%; min-height:60vh; font-size:15px; line-height:1.6;"><?php
					echo esc_textarea( $final ?: $draft );
				?></textarea>
				<p class="description">This is the version that gets recorded, archived, and fed forward as next-day context — never the raw draft above.</p>

				<?php submit_button( 'Save Final Script' ); ?>
			</form>
		</div>
		<script>
		document.getElementById('ng-toggle-draft').addEventListener('click', function () {
			var draft = document.getElementById('ng-ai-draft');
			var showing = draft.style.display !== 'none';
			draft.style.display = showing ? 'none' : 'block';
			this.textContent = showing ? 'Show AI draft' : 'Hide AI draft';
		});
		</script>
		<?php
	}

	private static function render_notices() {
		if ( isset( $_GET['ng_notice'] ) && 'saved' === $_GET['ng_notice'] ) {
			echo '<div class="notice notice-success is-dismissible"><p>Final script saved.</p></div>';
		}
	}
}
