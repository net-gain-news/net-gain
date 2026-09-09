<?php
/**
 * Talent-facing area (Spec Section 12: talent sees only their own assigned
 * show(s), plus any show(s) currently covering). The first screen in this
 * plugin that isn't admin-only - menu visibility uses the base "read"
 * capability (any logged-in user), with the real access check being the
 * talent-assignment relationship, not a WordPress role/capability.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_My_Show_Page {

	const SLUG = 'net-gain-my-show';

	public static function render() {
		$user_id = get_current_user_id();
		$assignments = Net_Gain_Talent_Assignments::list_for_user( $user_id );
		$show_ids = array_unique( array_map( function ( $row ) {
			return (int) $row['show_id'];
		}, $assignments ) );

		self::render_notices();
		?>
		<div class="wrap ng-my-show">
			<h1>My Show</h1>

			<?php if ( empty( $show_ids ) ) : ?>
				<p>You're not currently assigned to any show, as a primary host or as a covering substitute. If this seems wrong, check with your studio admin.</p>
			<?php else : ?>
				<?php foreach ( $show_ids as $show_id ) : ?>
					<?php self::render_show_card( $show_id ); ?>
				<?php endforeach; ?>
			<?php endif; ?>
		</div>
		<?php
	}

	private static function render_show_card( $show_id ) {
		$show = get_post( $show_id );
		if ( ! $show ) {
			return;
		}

		$episode = self::current_episode_for_show( $show_id );

		if ( $episode ) {
			$step_status  = get_post_meta( $episode->ID, 'ng_step_status', true ) ?: array();
			$reviewed     = $step_status['script_reviewed']['status'] ?? 'pending';
			$finalization = get_post_meta( $episode->ID, 'ng_finalization', true );
			$finalization = is_array( $finalization ) ? $finalization : array();
			$state        = $finalization['state'] ?? 'pending';
		}
		?>
		<div class="card" style="max-width:640px; padding:20px; margin-bottom:20px;">
			<h2><?php echo esc_html( $show->post_title ); ?></h2>

			<?php if ( ! $episode ) : ?>
				<p>No episode ready yet — waiting on script generation.</p>

			<?php elseif ( ! in_array( $reviewed, array( 'done', 'degraded' ), true ) ) : ?>
				<p>Today's script (<?php echo esc_html( get_post_meta( $episode->ID, 'ng_episode_date', true ) ); ?>) is ready for review.</p>
				<a class="button button-primary" href="<?php echo esc_url( add_query_arg( array( 'page' => Net_Gain_Script_Review_Page::SLUG, 'episode_id' => $episode->ID ), admin_url( 'admin.php' ) ) ); ?>">Review Script</a>

			<?php elseif ( 'counting_down' === $state ) : ?>
				<?php /* Classes, not ids, throughout this branch and the upload branch below - a talent covering/hosting multiple shows can have more than one of these cards live on the page at once (Section 4's many-to-many talent-show model), so per-episode state must live in data attributes, not page-unique ids. */ ?>
				<p>Audio received. Finalizing in <span class="ng-countdown" data-episode-id="<?php echo esc_attr( $episode->ID ); ?>" data-seconds="<?php echo esc_attr( self::seconds_remaining( $finalization ) ); ?>">--</span> seconds unless you act.</p>
				<p>
					<button type="button" class="button ng-abort" data-episode-id="<?php echo esc_attr( $episode->ID ); ?>">Abort (upload a different file)</button>
					<button type="button" class="button ng-publish-now" data-episode-id="<?php echo esc_attr( $episode->ID ); ?>">Publish Now (skip the wait)</button>
				</p>

			<?php elseif ( 'finalized' === $state ) : ?>
				<p>Finalized — queued, awaiting its scheduled publish time.</p>

			<?php else : /* pending or awaiting_replacement */ ?>
				<?php if ( 'awaiting_replacement' === $state ) : ?>
					<p>Aborted — upload a replacement file to restart finalization.</p>
				<?php else : ?>
					<p>Script reviewed. Upload today's recording to finalize.</p>
				<?php endif; ?>
				<button type="button" class="button button-primary ng-upload-audio" data-episode-id="<?php echo esc_attr( $episode->ID ); ?>">Upload Audio</button>
			<?php endif; ?>
		</div>
		<?php
	}

	private static function current_episode_for_show( $show_id ) {
		$episodes = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Episode::POST_TYPE,
				'post_parent'    => $show_id,
				'posts_per_page' => 1,
				'orderby'        => 'date',
				'order'          => 'desc',
			)
		);
		return $episodes ? $episodes[0] : null;
	}

	private static function seconds_remaining( $finalization ) {
		// countdown_started_at is stored in GMT (see class-rest-episode-steps.php)
		// so this must parse it as UTC explicitly rather than relying on
		// strtotime()'s ambiguous default-timezone behavior.
		$raw     = $finalization['countdown_started_at'] ?? 'now';
		$started = new DateTime( $raw, new DateTimeZone( 'UTC' ) );
		$total   = (int) ( $finalization['countdown_seconds'] ?? 90 );
		$elapsed = time() - $started->getTimestamp();
		return max( 0, $total - $elapsed );
	}

	private static function render_notices() {
		if ( isset( $_GET['ng_notice'] ) ) {
			$messages = array(
				'audio_uploaded' => 'Audio received — finalization countdown started.',
				'aborted'        => 'Aborted. Upload a replacement whenever you\'re ready.',
				'published_now'  => 'Finalized immediately.',
			);
			$notice = sanitize_key( wp_unslash( $_GET['ng_notice'] ) );
			if ( isset( $messages[ $notice ] ) ) {
				printf( '<div class="notice notice-success is-dismissible"><p>%s</p></div>', esc_html( $messages[ $notice ] ) );
			}
		}
	}
}
