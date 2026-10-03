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
			$step_status    = get_post_meta( $episode->ID, 'ng_step_status', true ) ?: array();
			$reviewed       = $step_status['script_reviewed']['status'] ?? 'pending';
			$finalization   = get_post_meta( $episode->ID, 'ng_finalization', true );
			$finalization   = is_array( $finalization ) ? $finalization : array();
			$state          = $finalization['state'] ?? 'pending';
			$images_status  = $step_status['images_rendered']['status'] ?? 'pending';
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
				<p><?php echo esc_html( self::finalized_message( $show_id, $episode->ID, $step_status ) ); ?></p>
				<p><?php Net_Gain_Audio_Replacement::render_control( $episode->ID ); ?></p>

			<?php else : /* pending or awaiting_replacement - script saved at least once, audio not yet received */ ?>
				<?php if ( 'awaiting_replacement' === $state ) : ?>
					<p>Aborted — upload a replacement file to restart finalization. Still need to fix the script first? Edit it below - it's not locked in until audio is uploaded.</p>
				<?php else : ?>
					<p>Script reviewed. Upload today's recording to finalize, or keep editing the script - it's not locked in until audio is uploaded.</p>
				<?php endif; ?>
				<p>
					<a class="button" href="<?php echo esc_url( add_query_arg( array( 'page' => Net_Gain_Script_Review_Page::SLUG, 'episode_id' => $episode->ID ), admin_url( 'admin.php' ) ) ); ?>">Edit Script</a>
					<button type="button" class="button button-primary ng-upload-audio" data-episode-id="<?php echo esc_attr( $episode->ID ); ?>">Upload Audio</button>
				</p>
			<?php endif; ?>

			<?php if ( $episode && in_array( $images_status, array( 'done', 'degraded' ), true ) ) : ?>
				<?php
				// Shown whenever images are ready, regardless of finalization state -
				// images render as soon as audio is received (Section 8.3), well
				// before publish time, specifically so a human can review them close
				// to when they're generated (Section 7's human review step), the same
				// reasoning as script review.
				$image_ids = array(
					'Podcast art' => (int) get_post_meta( $episode->ID, 'ng_image_square_id', true ),
					'YouTube art' => (int) get_post_meta( $episode->ID, 'ng_image_16x9_id', true ),
					'Website art' => (int) get_post_meta( $episode->ID, 'ng_image_1200x630_id', true ),
				);
				?>
				<hr>
				<p><strong>Episode images</strong><?php echo 'degraded' === $images_status ? ' (fallback used — AI generation didn\'t succeed this time)' : ''; ?></p>
				<div style="display:flex; gap:16px; flex-wrap:wrap; margin-bottom:12px;">
					<?php foreach ( $image_ids as $label => $attachment_id ) : ?>
						<?php if ( $attachment_id ) : ?>
							<div>
								<?php echo wp_get_attachment_image( $attachment_id, array( 120, 120 ), false, array( 'style' => 'display:block;object-fit:cover;' ) ); ?>
								<p class="description" style="margin:4px 0 0;"><?php echo esc_html( $label ); ?></p>
							</div>
						<?php endif; ?>
					<?php endforeach; ?>
				</div>
				<button type="button" class="button ng-regenerate-images" data-episode-id="<?php echo esc_attr( $episode->ID ); ?>" data-show-id="<?php echo esc_attr( $show_id ); ?>">Regenerate Images</button>
			<?php endif; ?>

			<?php self::render_earlier_episodes( $show_id, $episode ? $episode->ID : 0 ); ?>
		</div>
		<?php
	}

	/**
	 * Recent episodes other than the one the card above is about, collapsed by
	 * default - the host's way to reach an already-published episode to
	 * replace its audio (Spec Section 8.4) without crowding the daily view.
	 */
	private static function render_earlier_episodes( $show_id, $current_episode_id ) {
		$episodes = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Episode::POST_TYPE,
				'post_parent'    => $show_id,
				'posts_per_page' => 11,
				'orderby'        => 'date',
				'order'          => 'desc',
			)
		);
		$rows = array();
		foreach ( $episodes as $earlier ) {
			if ( (int) $earlier->ID === (int) $current_episode_id ) {
				continue;
			}
			if ( ! get_post_meta( $earlier->ID, 'ng_audio_attachment_id', true ) ) {
				continue; // nothing recorded yet, so nothing to replace.
			}
			$rows[] = $earlier;
		}
		if ( ! $rows ) {
			return;
		}
		?>
		<hr>
		<details>
			<summary style="cursor:pointer;">Earlier episodes — replace an audio file</summary>
			<table class="widefat striped" style="margin-top:10px;">
				<tbody>
				<?php foreach ( array_slice( $rows, 0, 10 ) as $earlier ) : ?>
					<tr>
						<td style="white-space:nowrap;"><?php echo esc_html( get_post_meta( $earlier->ID, 'ng_episode_date', true ) ); ?></td>
						<td><?php echo esc_html( $earlier->post_title ); ?></td>
						<td><?php Net_Gain_Audio_Replacement::render_control( $earlier->ID ); ?></td>
					</tr>
				<?php endforeach; ?>
				</tbody>
			</table>
		</details>
		<?php
	}

	/**
	 * What to tell the host about a finalized episode. "Finalized" only means
	 * the audio is locked in; by the time the host looks it has usually been
	 * published, and saying it is still waiting for its scheduled time then is
	 * wrong. Reports each destination's real state from the step statuses.
	 * YouTube is only counted for shows that have a channel connected.
	 */
	private static function finalized_message( $show_id, $episode_id, $step_status ) {
		$destinations = array(
			'captivate_published' => 'Captivate',
			'website_published'   => 'the website',
		);
		if ( Net_Gain_Secrets::exists( 'show', $show_id, 'youtube_oauth' ) ) {
			$destinations['youtube_published'] = 'YouTube';
		}

		$published = array();
		$pending   = array();
		$failed    = array();
		foreach ( $destinations as $step => $label ) {
			$status = $step_status[ $step ]['status'] ?? 'pending';
			if ( in_array( $status, array( 'done', 'degraded' ), true ) ) {
				$published[] = $label;
			} elseif ( 'failed' === $status ) {
				$failed[] = $label;
			} else {
				$pending[] = $label; // pending, queued or in_progress.
			}
		}

		if ( ! $published && ! $failed ) {
			return 'Finalized — queued, awaiting its scheduled publish time.';
		}

		$message = $published ? 'Published to ' . self::join_names( $published ) . '.' : 'Finalized.';
		if ( $pending ) {
			$message .= ' Still to come: ' . self::join_names( $pending ) . '.';
		}
		if ( $failed ) {
			$message .= ' Needs attention: ' . self::join_names( $failed ) . ' (an administrator has been alerted).';
		}
		return $message;
	}

	private static function join_names( array $names ) {
		if ( count( $names ) <= 1 ) {
			return implode( '', $names );
		}
		$last = array_pop( $names );
		return implode( ', ', $names ) . ' and ' . $last;
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
				'audio_uploaded'           => 'Audio received — finalization countdown started.',
				'aborted'                  => 'Aborted. Upload a replacement whenever you\'re ready.',
				'published_now'            => 'Finalized immediately.',
				'images_regenerate_queued' => 'Regeneration queued — the tick loop will pick this up on its next pass.',
				'audio_replacement_queued'  => 'Audio replaced. Where this episode is already published (Captivate, YouTube), the new file is being sent along in the background over the next few minutes.',
				'audio_replacement_retried' => 'Retrying the audio replacement on the next pass of the background job.',
			);
			$notice = sanitize_key( wp_unslash( $_GET['ng_notice'] ) );
			if ( isset( $messages[ $notice ] ) ) {
				printf( '<div class="notice notice-success is-dismissible"><p>%s</p></div>', esc_html( $messages[ $notice ] ) );
			}
		}
	}
}
